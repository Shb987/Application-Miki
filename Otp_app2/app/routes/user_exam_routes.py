
from fastapi import APIRouter, UploadFile, File, Form, Body, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi import BackgroundTasks
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
import pdfplumber
import uuid
import json
import os
import asyncio
from app.report.scert_pdf_professional import save_scert_question_paper
from fastapi import APIRouter, Query
from typing import List
from fastapi.responses import FileResponse
import os
from app.core.database import db

from app.utils.user_auth import get_current_user
from fastapi import Depends

router = APIRouter(tags=["User_Exam Module"])


def natural_sort_key(s):
    import re
    if not s:
        return []
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

async def fetch_student_by_id(student_id: str) -> Optional[dict]:
    if not student_id:
        return None
    student = None
    try:
        if ObjectId.is_valid(student_id):
            student = await db.students.find_one({"_id": ObjectId(student_id)})
    except Exception:
        pass
    if not student:
        student = await db.students.find_one({"_id": student_id})
    if not student:
        student = await db.students.find_one({"student_id": student_id})
    return student

def get_student_board_value(student: dict) -> Optional[str]:
    if not student:
        return None
    val = (
        student.get("syllabus") or 
        student.get("board") or 
        student.get("category") or 
        student.get("curriculum")
    )
    if val:
        v_str = str(val).strip().upper()
        if v_str in ["NCERT", "CBSE"]:
            return "NCERT"
        elif v_str in ["SCERT", "STATE", "KERALA"]:
            return "SCERT"
        return v_str
    return None

@router.get("/standard/{standard}")
async def get_subjects_and_chapters(standard: str, student_id: Optional[str] = None):
    import re
    query = {
        "standard": str(standard),
        "processed": True
    }
    fallback_query = {
        "standard": str(standard)
    }
    
    # If student_id is provided, fetch their syllabus dynamically and apply board filter
    if student_id:
        student = await fetch_student_by_id(student_id)
        if student:
            board_val = get_student_board_value(student)
            if board_val:
                if board_val.upper() in ["NCERT", "CBSE"]:
                    board_filter = {
                        "$or": [
                            {"board": {"$regex": "^(NCERT|CBSE)$", "$options": "i"}},
                            {"category": {"$regex": "^NCERT$", "$options": "i"}}
                        ]
                    }
                elif board_val.upper() in ["SCERT", "STATE", "KERALA"]:
                    board_filter = {
                        "$or": [
                            {"board": {"$regex": "^(SCERT|State|Kerala)$", "$options": "i"}},
                            {"category": {"$regex": "^SCERT$", "$options": "i"}}
                        ]
                    }
                else:
                    board_filter = {
                        "$or": [
                            {"board": {"$regex": f"^{re.escape(board_val)}$", "$options": "i"}},
                            {"category": {"$regex": f"^{re.escape(board_val)}$", "$options": "i"}}
                        ]
                    }
                query.update(board_filter)
                fallback_query.update(board_filter)
            
    # Fetch all processed textbooks for this standard (and category if applicable)
    docs = await db.textbook.find(query).to_list(None)

    # Optimization: List images once from the correct static directory
    IMAGE_DIR = os.path.join("app", "static", "subject_images")
    image_files = os.listdir(IMAGE_DIR) if os.path.exists(IMAGE_DIR) else []

    def get_subject_image(subject):
        if not subject:
            return None
        normalized_subject = subject.lower().replace(" ", "")
        
        # Manual mapping for common abbreviations or typos
        special_cases = {
            "english": "eng.jpg",
            "biology": "biolagy.jpg",
            "mathematics": "maths.jpg",
            "socialscience": "socialscience.jpg",
            "informationandtechnology": "IT.jpg",
            "informationandcommunicationtechnology": "IT.jpeg",
            "information&technology": "IT.jpeg",
            "information&communicationtechnology": "IT.jpeg",
            "socialscience-1": "socialscience.jpg"
        }
        
        if "information" in subject.lower():
            return "subject_images/IT.jpeg"
            
        if normalized_subject in special_cases:
            return f"subject_images/{special_cases[normalized_subject]}"
        else:
            # Search for loosely matching image
            for img in image_files:
                if img.lower().startswith(normalized_subject):
                    return f"subject_images/{img}"
                    
        # Fallback: match by name without extension
        for img in image_files:
            img_name = os.path.splitext(img)[0].lower()
            if img_name == normalized_subject:
                return f"subject_images/{img}"
        return None

    # Group chapters by subject first, then by textbook_name
    # subject_map: subject_name -> { textbook_name -> set(chapters) }
    subject_map = {}

    for doc in docs:
        subj = doc.get("subject")
        if not subj:
            continue
        tb_name = doc.get("textbook_name")
        if not tb_name or not tb_name.strip() or tb_name.strip().lower() == "null":
            tb_name = None
        else:
            tb_name = tb_name.strip()
            
        if subj not in subject_map:
            subject_map[subj] = {}
            
        if tb_name not in subject_map[subj]:
            subject_map[subj][tb_name] = set()
            
        chapter_list = doc.get("chapters", [])
        if isinstance(chapter_list, list):
            subject_map[subj][tb_name].update([c for c in chapter_list if c])

    # Fallback to textbook_chapters for any subjects/textbooks
    # that don't have chapters in db.textbook
    fallback_docs = await db.textbook_chapters.find(fallback_query).to_list(None)

    # Cache textbook_id -> textbook_name to avoid excessive DB calls
    textbook_cache = {}

    for fd in fallback_docs:
        subj = fd.get("subject")
        if not subj:
            continue
        t_id = fd.get("textbook_id")
        chap_title = fd.get("chapter_title")
        if not chap_title:
            continue

        tb_name = None
        if t_id:
            if t_id not in textbook_cache:
                try:
                    tb_doc = await db.textbook.find_one({"_id": ObjectId(t_id)})
                    if tb_doc:
                        name_val = tb_doc.get("textbook_name")
                        if name_val and name_val.strip() and name_val.strip().lower() != "null":
                            tb_name = name_val.strip()
                except Exception:
                    pass
                textbook_cache[t_id] = tb_name
            else:
                tb_name = textbook_cache[t_id]

        if subj not in subject_map:
            subject_map[subj] = {}
            
        if tb_name not in subject_map[subj]:
            subject_map[subj][tb_name] = set()
            
        subject_map[subj][tb_name].add(chap_title)

    result = []
    for subj, textbooks_dict in subject_map.items():
        textbook_list = []
        for tb_name, chapters_set in textbooks_dict.items():
            sorted_chaps = sorted(list(chapters_set), key=natural_sort_key)
            textbook_list.append({
                "textbook_name": tb_name,
                "chapters": sorted_chaps
            })
            
        # Sort textbooks alphabetically by textbook_name (handling None/null gracefully)
        textbook_list.sort(key=lambda x: (x["textbook_name"] is None, x["textbook_name"].lower() if x["textbook_name"] else ""))

        image_url = get_subject_image(subj)

        result.append({
            "name": subj,
            "textbook_name": textbook_list,
            "image_url": image_url
        })

    # Sort subjects alphabetically by name
    result.sort(key=lambda x: x["name"].lower() if x["name"] else "")

    return {
        "standard": standard,
        "subjects": result
    }




@router.get("/get-question-paper/{standard}/{subject}/{marks}")
async def get_generated_question_paper(
    standard: str, 
    subject: str, 
    marks: int,
    chapters: str,   # comma separated string
    current_user: dict = Depends(get_current_user)
):
    import re
    from app.routes.admin_exam_routes import _ensure_pdf_exists

    # Convert comma-separated string to list
    chapter_list = [c.strip() for c in (chapters or "").split(",") if c.strip()]

    # Convert standard to both int and str for flexible MongoDB matching
    std_str = str(standard).strip()
    try:
        std_int = int(std_str)
    except (ValueError, TypeError):
        std_int = None

    std_query = [std_str]
    if std_int is not None:
        std_query.append(std_int)

    # Step 1: Find tasks from question_tasks collection based on filters
    task_query = {
        "standard": {"$in": std_query},
        "subject": {"$regex": f"^{re.escape(subject.strip())}$", "$options": "i"}
    }
    if chapter_list:
        task_query["chapters"] = {"$in": chapter_list}
    if marks and marks > 0:
        task_query["marks"] = int(marks)

    tasks = await db.question_tasks.find(task_query).to_list(None)

    paper_doc = None
    if tasks:
        task_ids = [str(t["_id"]) for t in tasks]
        pipeline = [
            {"$match": {"task_id": {"$in": task_ids}}},
            {"$sample": {"size": 1}}
        ]
        papers = await db.generated_papers.aggregate(pipeline).to_list(1)
        if papers:
            paper_doc = papers[0]

    # Step 2: Direct Fallback Search in generated_papers collection
    if not paper_doc:
        direct_match = {
            "$or": [
                {"paper.standard": {"$in": std_query}},
                {"standard": {"$in": std_query}}
            ],
            "$or": [
                {"paper.subject": {"$regex": f"^{re.escape(subject.strip())}$", "$options": "i"}},
                {"subject": {"$regex": f"^{re.escape(subject.strip())}$", "$options": "i"}}
            ]
        }
        pipeline_direct = [
            {"$match": direct_match},
            {"$sample": {"size": 1}}
        ]
        papers = await db.generated_papers.aggregate(pipeline_direct).to_list(1)
        if papers:
            paper_doc = papers[0]

    # Step 3: Broad Search Fallback if no exact match
    if not paper_doc:
        pipeline_broad = [
            {
                "$match": {
                    "$or": [
                        {"paper.standard": {"$in": std_query}},
                        {"standard": {"$in": std_query}},
                        {"paper.subject": {"$regex": f"^{re.escape(subject.strip())}$", "$options": "i"}},
                        {"subject": {"$regex": f"^{re.escape(subject.strip())}$", "$options": "i"}}
                    ]
                }
            },
            {"$sample": {"size": 1}}
        ]
        papers = await db.generated_papers.aggregate(pipeline_broad).to_list(1)
        if papers:
            paper_doc = papers[0]

    if not paper_doc:
        return {
            "status": False,
            "message": f"No question paper found for Class {standard} {subject}.",
            "data": None
        }

    # Extract paper details
    paper = paper_doc.get("paper", {})
    actual_task_id = paper_doc.get("task_id", str(paper_doc.get("_id")))
    
    # Auto-heal / generate PDF on the fly and get cache-busted URL
    pdf_url = _ensure_pdf_exists(paper_doc, force_rerender=True)

    sections = paper.get("sections") or []

    paper_payload = {
        "paper_id": paper.get("paper_id") or str(paper_doc.get("_id")),
        "standard": paper.get("standard") or std_str,
        "subject": paper.get("subject") or subject,
        "title": paper.get("title") or f"QUESTION PAPER - CLASS {standard} {subject.upper()}",
        "time": paper.get("time") or "90 MINUTES",
        "marks": paper.get("marks") or marks,
        "chapters_used": paper.get("chapters_used") or chapter_list,
        "sections": sections
    }

    return {
        "status": True,
        "message": "Question paper retrieved successfully.",
        "data": {
            "task_id": actual_task_id,
            "paper_oid": str(paper_doc["_id"]),
            "paper_id": paper_payload["paper_id"],
            "standard": paper_payload["standard"],
            "subject": paper_payload["subject"],
            "chapters_used": paper_payload["chapters_used"],
            "sections": sections,
            "questions": sections,
            "paper": paper_payload,
            "marks": paper_payload["marks"],
            "pdf_url": pdf_url,
            "download_url": pdf_url,
            "pdf_path": paper_doc.get("pdf_path"),
            "created_at": paper_doc.get("created_at")
        }
    }


@router.get("/download-paper/{paper_id}")
async def download_paper(paper_id: str, current_user: dict = Depends(get_current_user)):

    # UPDATED: Find by MongoDB _id
    try:
        paper_doc = await db.generated_papers.find_one({
            "_id": ObjectId(paper_id)
        })
    except:
        # Fallback for legacy papers that might send the uuid string
        paper_doc = await db.generated_papers.find_one({
            "paper.paper_id": paper_id
        })

    if not paper_doc:
        return {
            "status": False,
            "message": "No paper found with this paper_id",
            "data": None
        }

    # Check canonical location in app/static/generated_papers
    paper_info = paper_doc.get("paper") or {}
    paper_id_code = paper_info.get("paper_id") or str(paper_doc.get("_id", "paper"))
    filename = f"{paper_id_code}.pdf"
    canonical_path = os.path.abspath(os.path.join("app", "static", "generated_papers", filename))

    db_pdf_path = paper_doc.get("pdf_path")
    full_path = None

    if os.path.isfile(canonical_path):
        full_path = canonical_path
    elif db_pdf_path and os.path.isfile(os.path.abspath(db_pdf_path)):
        full_path = os.path.abspath(db_pdf_path)
    else:
        # Re-render on the fly if missing
        if paper_info:
            try:
                raw_std = paper_info.get("standard") or paper_doc.get("standard") or 1
                try:
                    std = int(raw_std)
                except (ValueError, TypeError):
                    std = 1

                paper_info["standard"] = str(std)
                if std <= 5:
                    save_primary_question_paper(paper_info, canonical_path)
                else:
                    save_scert_question_paper(paper_info, canonical_path)

                if os.path.isfile(canonical_path):
                    full_path = canonical_path
            except Exception as e:
                print(f"[USER-EXAM-PDF] Auto-heal failed: {e}")

    if not full_path or not os.path.isfile(full_path):
        return {
            "status": False,
            "message": "PDF file not found in server storage.",
            "data": None
        }

    # Return file for download
    return FileResponse(
        path=full_path,
        filename=os.path.basename(full_path),
        media_type="application/pdf"
    )
