
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

@router.get("/standard/{standard}")
async def get_subjects_and_chapters(standard: str, category: str = "NCERT", student_id: Optional[str] = None):
    # If student_id is provided, fetch their category dynamically
    if student_id:
        try:
            student = await db.students.find_one({"_id": ObjectId(student_id)})
            if student and student.get("category"):
                category = student.get("category")
        except Exception:
            pass
            
    # Fetch all processed textbooks for this standard and category
    docs = await db.textbook.find({
        "standard": standard,
        "category": category,
        "processed": True
    }).to_list(None)

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
    fallback_docs = await db.textbook_chapters.find({
        "standard": standard
    }).to_list(None)

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
    chapters: str,   # <-- coming as comma separated string
    current_user: dict = Depends(get_current_user)
):

    # Convert comma-separated string to list
    chapter_list = [c.strip() for c in chapters.split(",")]

    # Step 1: Find all tasks from question_tasks collection based on filters
    tasks = await db.question_tasks.find({
        "standard": standard,
        "subject": subject,
        "chapters": {"$in": chapter_list},
        "marks": marks
    }).to_list(None)

    if not tasks:
        return {
            "status": False,
            "message": "No question task found for the given standard, subject, chapters and marks.",
            "data": None
        }

    # Extract all matching task IDs
    task_ids = [str(t["_id"]) for t in tasks]

    # Step 2: Find a random paper from any of these tasks
    pipeline = [
        {"$match": {"task_id": {"$in": task_ids}}},
        {"$sample": {"size": 1}}
    ]

    papers = await db.generated_papers.aggregate(pipeline).to_list(1)
    paper_doc = papers[0] if papers else None
    if not paper_doc:
        return {
            "status": False,
            "message": "Generated question paper not found for the given task IDs.",
            "data": None
        }

    # Extract the nested paper object
    paper = paper_doc.get("paper", {})
    actual_task_id = paper_doc.get("task_id", task_ids[0])

    # Step 3: Return combined response
    return {
        "status": True,
        "message": "Question paper retrieved successfully.",
        "data": {
            "task_id": actual_task_id,
            "paper_oid": str(paper_doc["_id"]),
            "paper_id": paper.get("paper_id"),
            "standard": paper.get("standard"),
            "subject": paper.get("subject"),
            "chapters_used": paper.get("chapters_used"),
            "sections": paper.get("sections"),
            "marks": marks,
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

    # PDF path stored in DB (e.g. "Exams/generated_papers/xxx.pdf")
    pdf_path = paper_doc.get("pdf_path")

    if not pdf_path:
        return {
            "status": False,
            "message": "PDF path not found in database.",
            "data": None
        }

    # Construct full file path
    full_path = os.path.join(os.getcwd(), pdf_path)

    # Check whether file exists
    if not os.path.isfile(full_path):
        return {
            "status": False,
            "message": "PDF file not found in server storage.",
            "data": full_path
        }

    # Return file for download
    return FileResponse(
        path=full_path,
        filename=os.path.basename(full_path),
        media_type="application/pdf"
    )
