


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
