


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

from core.database import db
from openai import OpenAI

router = APIRouter(tags=["User_Exam Module"])



@router.get("/standard/{standard}")
async def get_subjects_and_chapters(standard: str):
    # Step 1: Get subjects for the given standard
    subjects = await db.textbook.distinct("subject", {"standard": standard})
    subjects = sorted([s for s in subjects if s])

    result = []

    # Step 2: Build subject objects with chapters
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

        result.append({
            "name": subject,
            "chapters": sorted(list(chapters_set))
        })

    return {
        "standard": standard,
        "subjects": result
    }

# @router.get("/get-question-paper/{standard}/{subject}/{chapter}/{marks}")
# async def get_generated_question_paper(
#     standard: str, 
#     subject: str, 
#     chapter: str, 
#     marks: int
# ):

#     # Step 1: Find the task from question_tasks collection based on filters
#     task_doc = await db.question_tasks.find_one({
#         "standard": standard,
#         "subject": subject,
#         "chapters": {"$in": [chapter]},
#         "marks": marks
#     })

#     if not task_doc:
#         return {
#             "status": False,
#             "message": "No question task found for the given standard, subject, chapter and marks.",
#             "data": None
#         }

#     task_id = task_doc.get("task_id")

#     # Step 2: Using task_id, find the generated question paper
#     paper_doc = await db.generated_papers.find_one({
#         "task_id": task_id
#     })

#     if not paper_doc:
#         return {
#             "status": False,
#             "message": "Generated question paper not found for the given task_id.",
#             "data": None
#         }

#     # Extract the nested paper object
#     paper = paper_doc.get("paper", {})

#     # Step 3: Return combined response
#     return {
#         "status": True,
#         "message": "Question paper retrieved successfully.",
#         "data": {
#             "task_id": task_id,
#             "paper_id": paper.get("paper_id"),
#             "standard": paper.get("standard"),
#             "subject": paper.get("subject"),
#             "chapters_used": paper.get("chapters_used"),
#             "sections": paper.get("sections"),
#             "marks": marks,  # Added marks here

#             # PDF path from top-level generated_papers
#             "pdf_path": paper_doc.get("pdf_path"),

#             # created_at from top-level
#             "created_at": paper_doc.get("created_at")
#         }
#     }
from fastapi import APIRouter, Query
from typing import List

# @router.get("/get-question-paper/{standard}/{subject}/{marks}")
# async def get_generated_question_paper(
#     standard: str,
#     subject: str,
#     marks: int,
#     chapters: List[str] = Query(..., description="List of chapter names")
# ):
#     # Step 1: Find the task based on standard, subject, selected chapters, and marks
#     task_doc = await db.question_tasks.find_one({
#         "standard": standard,
#         "subject": subject,
#         "chapters": {"$all": chapters},  # Matches documents containing all selected chapters
#         "marks": marks
#     })

#     if not task_doc:
#         return {
#             "status": False,
#             "message": "No question task found for the given standard, subject, chapters and marks.",
#             "data": None
#         }

#     task_id = task_doc.get("task_id")

#     # Step 2: Get the generated question paper
#     paper_doc = await db.generated_papers.find_one({"task_id": task_id})

#     if not paper_doc:
#         return {
#             "status": False,
#             "message": "Generated question paper not found for the given task_id.",
#             "data": None
#         }

#     paper = paper_doc.get("paper", {})

#     # Step 3: Return response
#     return {
#         "status": True,
#         "message": "Question paper retrieved successfully.",
#         "data": {
#             "task_id": task_id,
#             "paper_id": paper.get("paper_id"),
#             "standard": paper.get("standard"),
#             "subject": paper.get("subject"),
#             "chapters_used": paper.get("chapters_used"),  # Already a list of strings
#             "sections": paper.get("sections"),
#             "marks": marks,
#             "pdf_path": paper_doc.get("pdf_path"),
#             "created_at": paper_doc.get("created_at")
#         }
#     }
from models.paper_models import QuestionPaperRequest
@router.post("/get-question-paper/{standard}/{subject}/{marks}")
async def get_generated_question_paper(
    standard: str,
    subject: str,
    marks: int,
    body: QuestionPaperRequest
):

    chapters = body.chapters  # Get chapters list from the body

    # Step 1: Find the task based on standard, subject, selected chapters, and marks
    task_doc = await db.question_tasks.find_one({
        "standard": standard,
        "subject": subject,
        "chapters": {"$all": chapters},
        "marks": marks
    })

    if not task_doc:
        return {
            "status": False,
            "message": "No question task found for the given standard, subject, chapters and marks.",
            "data": None
        }

    task_id = task_doc.get("task_id")

    # Step 2: Get the generated question paper
    paper_doc = await db.generated_papers.find_one({"task_id": task_id})

    if not paper_doc:
        return {
            "status": False,
            "message": "Generated question paper not found for the given task_id.",
            "data": None
        }

    paper = paper_doc.get("paper", {})

    # Step 3: Return response
    return {
        "status": True,
        "message": "Question paper retrieved successfully.",
        "data": {
            "task_id": task_id,
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



from fastapi.responses import FileResponse
import os

@router.get("/download-paper/{paper_id}")
async def download_paper(paper_id: str):

    # Find the document containing this paper_id
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
