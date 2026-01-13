


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
from report.scert_pdf_professional import save_scert_question_paper
from fastapi import APIRouter, Query
from typing import List
from fastapi.responses import FileResponse
import os
from core.database import db
from openai import OpenAI

router = APIRouter(tags=["User_Exam Module"])


@router.get("/standard/{standard}")
async def get_subjects_and_chapters(standard: str):
    # Step 1: Get subjects for the given standard
    subjects = await db.textbook.distinct("subject", {"standard": standard})
    subjects = sorted([s for s in subjects if s])

    # Optimization: List images once
    image_files = os.listdir("Subject_images") if os.path.exists("Subject_images") else []
    
    result = []
    
    for subject in subjects:
        chapters_set = set()

        # Primary: chapters from processed textbooks
        docs = await db.textbook.find({
            "standard": standard,
            "subject": subject,
            "processed": True
        }).to_list(None)

        for d in docs:
            chapter_list = d.get("chapters", [])
            if isinstance(chapter_list, list):
                chapters_set.update([c for c in chapter_list if c])

        # Fallback: textbook_chapters
        if not chapters_set:
            ch_docs = await db.textbook_chapters.find({
                "standard": standard,
                "subject": subject
            }).to_list(None)

            for cd in ch_docs:
                title = cd.get("chapter_title")
                if title:
                    chapters_set.add(title)

        # Image matching logic
        normalized_subject = subject.lower().replace(" ", "")
        
        # Manual mapping
        special_cases = {
            "english": "eng.jpg",
            "biology": "biolagy.jpg"
        }
        
        image_url = None
        
        if normalized_subject in special_cases:
            target_image = special_cases[normalized_subject]
            if target_image in image_files:
                image_url = f"subject_images/{target_image}"
        else:
            # Search for loosely matching image
            for img in image_files:
                if img.lower().startswith(normalized_subject):
                    image_url = f"subject_images/{img}"
                    break
        
        # Fallback: match by name without extension
        if not image_url:
             for img in image_files:
                img_name = os.path.splitext(img)[0].lower()
                if img_name == normalized_subject:
                    image_url = f"subject_images/{img}"
                    break

        result.append({
            "name": subject,
            "chapters": sorted(list(chapters_set)),
            "image_url": image_url
        })

    return {
        "standard": standard,
        "subjects": result
    }


from typing import List

from utils.user_auth import get_current_user
from fastapi import Depends

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

    # Step 1: Find the task from question_jobs collection based on filters
    task_doc = await db.question_tasks.find_one({
        "standard": standard,
        "subject": subject,
        "chapters": {"$in": chapter_list},   # <-- supports single/multiple
        "marks": marks
    })

    if not task_doc:
        return {
            "status": False,
            "message": "No question task found for the given standard, subject, chapters and marks.",
            "data": None
        }

    # task_id = task_doc.get("task_id")
    # UPDATED: Use the MongoDB _id string as task_id
    task_id = str(task_doc["_id"])

    # Step 2: Using task_id, find the generated question paper
    # Note: admin_routes stores the task_oid as 'task_id' in generated_papers
    paper_doc = await db.generated_papers.find_one({
        "task_id": task_id
    })

    if not paper_doc:
        return {
            "status": False,
            "message": "Generated question paper not found for the given task_id.",
            "data": None
        }

    # Extract the nested paper object
    paper = paper_doc.get("paper", {})

    # Step 3: Return combined response
    return {
        "status": True,
        "message": "Question paper retrieved successfully.",
        "data": {
            "task_id": task_id,
            "paper_oid": str(paper_doc["_id"]),  # NEW: MongoDB ID for download
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
