
from fastapi import APIRouter, UploadFile, File, Form, Body, HTTPException, Request, BackgroundTasks
from datetime import datetime, timezone
from typing import List, Optional
from bson import ObjectId
import pdfplumber
import uuid
import json
import os
import asyncio
from app.report.scert_pdf_professional import save_scert_question_paper
from app.report.primary_pdf_layout import save_primary_question_paper
from app.utils.admin_auth import require_permission
from fastapi import Depends
from app.core.database import db
from openai import AsyncOpenAI
import base64
import io
from PIL import Image
import pymupdf  # Standard PyMuPDF import

# --------------------------
# CONFIGURATION / CONSTANTS
# --------------------------

# OpenAI Client (Async — non-blocking event loop)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or "sk-placeholder")
print("OpenAI AsyncClient Initialized Successfully!")

router = APIRouter(tags=["Exam Module"])

UPLOAD_DIR = "app/static/textbook"
os.makedirs(UPLOAD_DIR, exist_ok=True)

GENERATED_PDF_DIR = "app/static/generated_papers"
os.makedirs(GENERATED_PDF_DIR, exist_ok=True)


async def log_admin_activity(username: str, role: str, action: str, details: str, status: str = "success"):
    await db.admin_activity_logs.insert_one({
        "username": username,
        "role": role,
        "action": action,
        "status": status,
        "details": details,
        "timestamp": datetime.now(timezone.utc),
    })


def determine_language_from_subject(subject: str, text_sample: str = None) -> str:
    """
    Language Routing Approach:
    - If subject is 'Hindi' or contains 'hindi' -> 'hi' (Hindi prompt)
    - If subject is 'Malayalam' or contains 'malayalam' -> 'ml' (Malayalam prompt)
    - All other subjects (English, Science, Maths, Social Science, etc.) -> 'en' (English prompt)
    """
    subj_clean = (subject or "").strip().lower()
    if "hindi" in subj_clean or subj_clean == "hi":
        return "hi"
    elif "malayalam" in subj_clean or subj_clean == "ml":
        return "ml"
    return "en"



# --------------------------
# EXAM BLUEPRINTS
# --------------------------

PRIMARY_PEDAGOGY_PROMPT = """
You are a friendly Primary School Teacher (Standard 1-5). Your task is to generate a fun and engaging question paper.

### CRITICAL ACCURACY & LOGIC RULES ###
1. **Logical Consistency**: Avoid "logic-less" questions. If a question is about a "Rectangle", do NOT include "Rectangle" as one of the multiple-choice options. The options should be distinct from the subject of the question.
2. **No Missing Visuals**: NEVER generate questions like "Look at the picture" or "Complete the pattern" if the visual is not shown.
3. **Self-Contained Questions**: If a question relies on an illustration, describe it (e.g., "In a picture, there are 3 big circles...").
4. **No Hallucinations**: Only use characters/objects named in the textbook.
5. **Match Integrity**: Ensure left and right columns in 'Match' questions have perfect, balanced pairs.
6. **No Redundant Phrasing**: DO NOT prepend the question with "Fill in the blank:", "True or False:", or "Answer the following:". Just ask the question directly.

### PEDAGOGY ###
- Language: Use very simple English.
- Engagement: Encourage the student!
"""

# --------------------------
# UTILITIES
# --------------------------

def _safe(obj, key, default=""):
    return obj.get(key, default) if isinstance(obj, dict) else default

def get_exam_structure(standard: int, total: int):
    """
    Blueprint mapping according to official grade standards and total marks:
    - Primary (1-5): 30 Marks & 50 Marks
    - Middle (6-8): 50 Marks & 80 Marks
    - High School (9-10): 40 Marks & 80 Marks
    - Plus Two (11-12): 60 Marks & 80 Marks
    """
    # Primary Standards (1-5)
    if standard <= 5:
        if total == 30:
            allowed_types = ["MCQ", "FillInTheBlanks", "MatchTheFollowing", "TrueFalse", "PictureBased", "VeryShort"]
            sections = {"A": (1, 10), "B": (2, 5), "C": (5, 2)}
            return (allowed_types, sections)
        else:  # Default 50 marks
            allowed_types = ["MCQ", "FillInTheBlanks", "MatchTheFollowing", "TrueFalse", "PictureBased", "VeryShort", "Short"]
            sections = {"A": (1, 10), "B": (2, 5), "C": (3, 5), "D": (5, 3)}
            return (allowed_types, sections)

    # Middle Standards (6-8)
    if standard <= 8:
        if total == 80:
            allowed_types = ["MCQ", "FillInTheBlanks", "TrueFalse", "VeryShort", "Short", "ShortEssay", "Reasoning"]
            sections = {"A": (1, 6), "B": (2, 6), "C": (3, 10), "D": (4, 8)}
            return (allowed_types, sections)
        else:  # Default 50 marks
            allowed_types = ["MCQ", "FillInTheBlanks", "TrueFalse", "VeryShort", "Short", "Reasoning"]
            sections = {"A": (1, 10), "B": (2, 5), "C": (3, 5), "D": (5, 3)}
            return (allowed_types, sections)

    # High School Standards (9-10)
    if standard in [9, 10]:
        if total == 40:
            allowed_types = ["MCQ", "VeryShort", "Short", "Essay", "Apply", "Analyze"]
            sections = {"A": (1, 8), "B": (2, 6), "C": (3, 4), "D": (4, 2)}
            return (allowed_types, sections)
        else:  # Default 80 marks
            allowed_types = ["MCQ", "VeryShort", "Short", "Essay", "Apply", "Analyze", "CaseStudy"]
            sections = {"A": (1, 8), "B": (2, 6), "C": (3, 10), "D": (5, 6)}
            return (allowed_types, sections)

    # Plus Two Standards (11-12)
    if total == 60:
        allowed_types = ["MCQ", "Short", "Essay", "Apply", "Analyze", "CaseStudy", "Diagram"]
        sections = {"A": (1, 10), "B": (2, 5), "C": (3, 5), "D": (5, 5)}
        return (allowed_types, sections)
    else:  # Default 80 marks
        allowed_types = ["MCQ", "Short", "Essay", "Apply", "Analyze", "CaseStudy", "Diagram"]
        sections = {"A": (1, 10), "B": (2, 5), "C": (3, 5), "D": (4, 5), "E": (5, 5)}
        return (allowed_types, sections)

def normalize_text(text: str) -> str:
    """Collapses characters separated by spaces and artifacts like 'WWeeaatthheerr'."""
    if not text: return ""
    import re
    import unicodedata
    
    # 0. Clean Latin diacritics (e.g., Nāṭyaśāstra -> Natyasastra) to prevent rendering black boxes (■)
    normalized = unicodedata.normalize('NFD', text)
    text = "".join(c for c in normalized if not (0x0300 <= ord(c) <= 0x036F))
    text = unicodedata.normalize('NFC', text)

    # 1. Collapse characters separated by spaces (G e n e t i c s -> Genetics)
    text = re.sub(r'(?<=\b[A-Za-z]) (?=[A-Za-z]\b)', '', text)
    # 2. Handle "1 1" -> "1" (common PDF artifact for numbers)
    text = re.sub(r'(\b\d)\s+(\d\b)', r'\1\2', text)
    # 3. Handle doubled letters (WWeeaatthheerr -> Weather)
    def de_double(m):
        s = m.group(0)
        if len(s) >= 4 and all(s[i] == s[i+1] for i in range(0, len(s), 2)):
            fixed = "".join([s[i] for i in range(0, len(s), 2)])
            return fixed
        return s
    text = re.sub(r'([A-Za-z])\1([A-Za-z])\2', de_double, text)
    return text

async def extract_text_via_vision(file_path: str, status_query: dict = None) -> str:
    """Converts PDF pages to images and uses GPT-4o-mini Vision to extract text."""
    print(f"[VISION-EXTRACT] Starting Vision-based extraction for: {file_path}")
    combined_text = ""
    try:
        doc = pymupdf.open(file_path)
        for i in range(len(doc)):
            print(f"[VISION-EXTRACT] Processing Page {i+1}/{len(doc)}...")
            page = doc.load_page(i)
            # Higher DPI for better OCR quality
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
            img_data = pix.tobytes("png")
            base64_image = base64.b64encode(img_data).decode('utf-8')

            print(f"[VISION-EXTRACT] Sending Page {i+1} to OpenAI Vision API...")
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all educational text from this textbook page. Preserve the logical reading order. Ignore decorative elements but include captions and diagram labels."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                            },
                        ],
                    }
                ],
                max_tokens=2000,
            )
            page_text = response.choices[0].message.content
            combined_text += page_text + "\n\n"
            print(f"[VISION-EXTRACT] Page {i+1} extracted successfully.")
            
            if status_query:
                progress_pct = 10 + int(((i + 1) / len(doc)) * 39)
                await db.chapter_status.update_one(
                    status_query,
                    {"$set": {"progress": progress_pct, "updated_at": datetime.now(timezone.utc)}}
                )
        
        doc.close()
        return combined_text
    except Exception as e:
        print(f"[VISION-EXTRACT] CRITICAL ERROR during vision extraction: {e}")
        return ""

def validate_fix_marks(paper: dict, required_total: int):
    total = sum(q.get("marks", 0) for q in paper["questions"])
    diff = required_total - total
    if diff != 0 and paper["questions"]:
        paper["questions"][-1]["marks"] += diff
    return paper


@router.post("/textbook/upload-batch")
async def upload_chapter_endpoint(
    background_tasks: BackgroundTasks,
    board: str = Form(...),
    standard: str = Form(...),
    state: str = Form(...),
    subject: str = Form(...),
    chapter_name: str = Form(...),
    chapter_number: str = Form(...),
    textbook_name: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    publication_year: str = Form(...),
    force_vision: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_admin: dict = Depends(require_permission("Exams, Textbooks & Syllabus", "create"))
):
    """
    Handle single chapter PDF upload. Immediately saves metadata and triggers
    background processing (extraction + embedding).
    """
    try:
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")

        # 1. Save PDF
        file_id = str(uuid.uuid4())
        filename = f"ch_{chapter_number}_{file_id}.pdf"
        file_path = os.path.join(UPLOAD_DIR, filename)

        with open(file_path, "wb") as f:
            f.write(await file.read())

        # 2. Prepare Chapter Record in 'textbook' collection
        textbook_query = {
            "board": board,
            "standard": standard,
            "state": state,
            "subject": subject,
            "publication_year": publication_year
        }

        if textbook_name and textbook_name.strip() and textbook_name.strip().lower() != "null":
            textbook_query["textbook_name"] = textbook_name.strip()
        else:
            textbook_query["textbook_name"] = None

        if category and category.strip() and category.strip().lower() != "null":
            textbook_query["category"] = category.strip()
        else:
            textbook_query["category"] = None

        full_chapter_title = f"{chapter_number} {chapter_name}".strip()

        # Update/Reset chapter status in parent textbook
        await db.textbook.update_one(
            textbook_query,
            {
                "$addToSet": {"chapters": full_chapter_title},
                "$setOnInsert": {
                    "created_at": datetime.now(timezone.utc),
                    "processed": True,
                    "status": "completed",
                    "progress": 100
                }
            },
            upsert=True
        )

        # 2.5 Initialize Chapter Status for UI Polling
        await db.chapter_status.update_one(
            {
                "board": board,
                "standard": standard,
                "state": state,
                "subject": subject,
                "textbook_name": textbook_query["textbook_name"],
                "publication_year": publication_year,
                "chapter_title": full_chapter_title
            },
            {
                "$set": {
                    "status": "processing",
                    "updated_at": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )

        activity_log = await db.admin_activity_logs.insert_one({
            "username": current_admin["sub"],
            "role": current_admin["role"],
            "action": "upload_textbook",
            "status": "processing",
            "details": f"Uploading textbook chapter {chapter_number}: {chapter_name} for Class {standard} {subject} ({board})",
            "timestamp": datetime.now(timezone.utc),
        })

        # 3. Queue Background Processing
        background_tasks.add_task(
            process_chapter_worker,
            textbook_query=textbook_query,
            full_chapter_title=full_chapter_title,
            file_path=file_path,
            original_filename=file.filename,
            initiated_by_username=current_admin["sub"],
            initiated_by_role=current_admin["role"],
            activity_log_id=str(activity_log.inserted_id),
            force_vision=(force_vision == "true")
        )

        return {
            "status": "processing",
            "message": f"Chapter '{full_chapter_title}' received. Processing started in background.",
        }
    except HTTPException as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "upload_textbook",
            f"Failed to upload textbook chapter {chapter_number}: {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "upload_textbook",
            f"Failed to upload textbook chapter {chapter_number}: {exc}",
            status="failed",
        )
        raise

async def process_chapter_worker(
    textbook_query,
    full_chapter_title,
    file_path,
    original_filename,
    initiated_by_username: str | None = None,
    initiated_by_role: str | None = None,
    activity_log_id: str | None = None,
    force_vision: bool = False
):
    """Background worker to extract text and generate embeddings for a single chapter."""
    status_query = {
        "board": textbook_query.get("board"),
        "standard": textbook_query.get("standard"),
        "state": textbook_query.get("state"),
        "subject": textbook_query.get("subject"),
        "textbook_name": textbook_query.get("textbook_name"),
        "publication_year": textbook_query.get("publication_year"),
        "chapter_title": full_chapter_title
    }
    try:
        print(f"[BG-CHAPTER] Processing: {full_chapter_title} ({original_filename})")
        
        # 1. Extract Text
        print(f"[BG-CHAPTER] Step 1: Extracting text (File: {file_path})")
        
        await db.chapter_status.update_one(
            status_query,
            {"$set": {"progress": 10, "updated_at": datetime.now(timezone.utc)}}
        )
        text_content = ""
        
        # Branching: Use Vision ONLY if explicitly forced by toggle
        standard_val = int(textbook_query.get("standard", 0))
        use_vision = force_vision
        
        if use_vision:
            print(f"[BG-CHAPTER] Force Vision Extraction toggle enabled. Using VISION-BASED extraction.")
            text_content = await extract_text_via_vision(file_path, status_query)
        else:
            print(f"[BG-CHAPTER] Using standard text extraction (pdfplumber)...")
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                for idx, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    # Filter fragmented lines
                    lines = page_text.split('\n')
                    cleaned_lines = [l.strip() for l in lines if l.strip() and not (len(l.strip()) < 3 and l.strip().isdigit())]
                    text_content += "\n".join(cleaned_lines) + "\n"
                    
                    # Update progress: 10% to 49%
                    progress_pct = 10 + int(((idx + 1) / total_pages) * 39)
                    await db.chapter_status.update_one(
                        status_query,
                        {"$set": {"progress": progress_pct, "updated_at": datetime.now(timezone.utc)}}
                    )
            
            text_content = normalize_text(text_content)

        if not text_content.strip():
            print(f"[BG-CHAPTER] ERROR: Extraction failed completely (No text from pdfplumber or vision).")
            await db.chapter_status.update_one(
                status_query,
                {"$set": {"status": "failed", "error": "No readable text found (PDF might be an image/scan). Try using an OCR-processed version.", "updated_at": datetime.now(timezone.utc)}}
            )
            return

        # 2. Get Textbook ID
        print(f"[BG-CHAPTER] Step 2: Retrieving textbook metadata...")
        textbook_doc = await db.textbook.find_one(textbook_query)
        if not textbook_doc:
            print(f"[BG-CHAPTER] Error: Textbook container not found for {textbook_query}")
            await db.chapter_status.update_one(
                status_query,
                {"$set": {"status": "failed", "error": "Textbook metadata not found", "updated_at": datetime.now(timezone.utc)}}
            )
            return
        textbook_id = str(textbook_doc["_id"])

        # 2.5. Determine Language based on Subject (Hindi -> hi, Malayalam -> ml, Others -> en)
        subject_name = textbook_query.get("subject", "")
        print(f"[BG-CHAPTER] Step 2.5: Determining language for subject '{subject_name}'...")
        detected_language = determine_language_from_subject(subject_name, text_content[:2000])
        print(f"[BG-CHAPTER] Subject '{subject_name}' -> Language set to '{detected_language}'")
        
        # Save detected language to chapter status
        await db.chapter_status.update_one(
            status_query,
            {"$set": {"detected_language": detected_language}}
        )

        # 3. Generate Embeddings & Save Passages
        print(f"[BG-CHAPTER] Step 3: Generating embeddings for {len(text_content)} characters...")
        
        await db.chapter_status.update_one(
            status_query,
            {"$set": {"progress": 50, "updated_at": datetime.now(timezone.utc)}}
        )
        
        PASSAGE_SIZE = 4000
        PASSAGE_OVERLAP = 400
        passages = []
        
        if len(text_content) <= PASSAGE_SIZE:
            passages.append(text_content)
        else:
            for i in range(0, len(text_content), PASSAGE_SIZE - PASSAGE_OVERLAP):
                passages.append(text_content[i:i + PASSAGE_SIZE])

        valid_docs = []
        embedding_errors = []   # Collect all error messages for reporting
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key == "sk-placeholder":
            err_msg = "OPENAI_API_KEY is not configured in .env. Cannot generate text embeddings — please set a valid OpenAI API key and re-upload."
            print(f"[BG-CHAPTER] WARNING: {err_msg}")
            await db.chapter_status.update_one(
                status_query,
                {"$set": {"status": "failed", "error": err_msg, "updated_at": datetime.now(timezone.utc)}}
            )
            if activity_log_id and initiated_by_username and initiated_by_role:
                await db.admin_activity_logs.update_one(
                    {"_id": ObjectId(activity_log_id)},
                    {"$set": {"status": "failed", "details": f"Failed to upload textbook chapter {full_chapter_title}: {err_msg}"}}
                )
            return
        else:
            for p_idx, passage in enumerate(passages):
                try:
                    emb = await client.embeddings.create(model="text-embedding-3-large", input=passage)
                    vector = emb.data[0].embedding
                    
                    # Log usage
                    if hasattr(emb, 'usage') and emb.usage:
                        from app.utils.ai_usage_logger import log_ai_usage
                        await log_ai_usage("ADMIN", "Chapter Upload - Embedding", "text-embedding-3-large", emb.usage)
                    
                    valid_docs.append({
                        "textbook_id": textbook_id,
                        "board": textbook_query["board"],
                        "standard": textbook_query["standard"],
                        "state": textbook_query["state"],
                        "subject": textbook_query["subject"],
                        "publication_year": textbook_query.get("publication_year"),
                        "chapter_title": full_chapter_title,
                        "content": passage.strip(),
                        "passage_index": p_idx,
                        "vector": vector,
                        "detected_language": detected_language,
                        "created_at": datetime.now(timezone.utc),
                    })
                    
                    # Update progress percentage (scale 50% to 99%)
                    progress_pct = 50 + int(((p_idx + 1) / len(passages)) * 49)
                    await db.chapter_status.update_one(
                        status_query,
                        {"$set": {"progress": progress_pct, "updated_at": datetime.now(timezone.utc)}}
                    )
                except Exception as e:
                    err_str = str(e)
                    embedding_errors.append(err_str)
                    print(f"[BG-CHAPTER] Embedding error [P{p_idx}]: {err_str}")

        # --- Graceful failure: detect why ALL passages failed ---
        if not valid_docs and embedding_errors:
            first_error = embedding_errors[0]
            # Identify common failure reasons and produce a human-readable message
            if "credit_balance_exhausted" in first_error or "insufficient_quota" in first_error:
                friendly_error = (
                    "⚠️ OpenAI Credits Exhausted: Your OpenAI API account has no remaining credits. "
                    "Please top up your balance at https://platform.openai.com/settings/organization/billing "
                    "and then re-upload this chapter."
                )
            elif "invalid_api_key" in first_error or "Incorrect API key" in first_error:
                friendly_error = (
                    "🔑 Invalid OpenAI API Key: The API key in your .env file is incorrect or has been revoked. "
                    "Please set a valid OPENAI_API_KEY and restart the server."
                )
            elif "RateLimitError" in first_error or "rate_limit" in first_error:
                friendly_error = (
                    "⏳ OpenAI Rate Limit Hit: Too many requests were sent in a short time. "
                    "Please wait a few minutes and try re-uploading."
                )
            elif "Connection" in first_error or "timeout" in first_error.lower():
                friendly_error = (
                    "🌐 Network Error: Could not reach the OpenAI API. "
                    "Please check your internet connection and re-upload."
                )
            else:
                friendly_error = f"Embedding generation failed for all passages. Reason: {first_error}"

            print(f"[BG-CHAPTER] FATAL: All {len(passages)} passages failed to embed. Marking as failed.")
            await db.chapter_status.update_one(
                status_query,
                {"$set": {"status": "failed", "error": friendly_error, "updated_at": datetime.now(timezone.utc)}}
            )
            if activity_log_id and initiated_by_username and initiated_by_role:
                await db.admin_activity_logs.update_one(
                    {"_id": ObjectId(activity_log_id)},
                    {"$set": {"status": "failed", "details": f"Failed to upload textbook chapter {full_chapter_title}: {friendly_error}"}}
                )
            return

        if valid_docs:
            # Atomic update: clear old and insert new
            await db.textbook_chapters.delete_many({
                "textbook_id": textbook_id,
                "chapter_title": full_chapter_title
            })
            await db.textbook_chapters.insert_many(valid_docs)
            await db.chapter_status.update_one(
                status_query,
                {"$set": {"status": "completed", "progress": 100, "updated_at": datetime.now(timezone.utc)}}
            )
            if activity_log_id and initiated_by_username and initiated_by_role:
                await db.admin_activity_logs.update_one(
                    {"_id": ObjectId(activity_log_id)},
                    {"$set": {"status": "completed", "details": f"Uploaded textbook chapter {full_chapter_title} for {textbook_query['subject']} ({textbook_query['board']})"}}
                )
            print(f"[BG-CHAPTER] SUCCESS: '{full_chapter_title}' processed with {len(valid_docs)} passages.")

    except Exception as e:
        print(f"[BG-CHAPTER] CRITICAL WORKER ERROR: {e}")
        await db.chapter_status.update_one(
            status_query,
            {"$set": {"status": "failed", "error": str(e), "updated_at": datetime.now(timezone.utc)}}
        )
        if activity_log_id and initiated_by_username and initiated_by_role:
            await db.admin_activity_logs.update_one(
                {"_id": ObjectId(activity_log_id)},
                {"$set": {"status": "failed", "details": f"Failed to upload textbook chapter {full_chapter_title}: {e}"}}
            )
    finally:
        # Auto-Cleanup: Delete the PDF after processing (success or failure)
        file_abspath = os.path.abspath(file_path)
        print(f"[BG-DEBUG] Checking file for cleanup: {file_abspath}")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[BG-DEBUG] Cleanup SUCCESS: Deleted temporary file {file_path}")
            except Exception as e:
                print(f"[BG-DEBUG] Cleanup FAILED: Could not delete {file_path}. Error: {e}")
        else:
            print(f"[BG-DEBUG] Cleanup SKIPPED: File already gone or doesn't exist at {file_path}")
        
        print(f"[BG-DEBUG] Worker finished for {full_chapter_title}")

# LEGACY TEXTBOOK SPLITTER REMOVED - Using Per-Chapter Uploads

# --------------------------
# ROUTES - STANDARDS / SUBJECTS / CHAPTERS
# --------------------------

@router.get("/standards")
async def get_standards():
    standards = await db.textbook.distinct("standard")
    try:
        standards_sorted = sorted(standards, key=lambda x: int(x))
    except:
        standards_sorted = sorted(standards)
    return {"standards": standards_sorted}

@router.get("/subjects/{standard}")
async def get_subjects(standard: str):
    subjects = await db.textbook.distinct("subject", {"standard": standard})
    subjects = sorted([s for s in subjects if s])
    return {"subjects": subjects}

def natural_sort_key(s):
    import re
    if not s:
        return []
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

@router.get("/chapters/{standard}/{subject}")
async def get_chapters(standard: str, subject: str):
    docs = await db.textbook.find({"standard": standard, "subject": subject, "processed": True}).to_list(None)
    chapter_set = []
    for d in docs:
        chs = d.get("chapters")
        if isinstance(chs, list):
            for c in chs:
                if c and c not in chapter_set:
                    chapter_set.append(c)
    if not chapter_set:
        ch_docs = await db.textbook_chapters.find({"standard": standard, "subject": subject}).to_list(None)
        for cd in ch_docs:
            title = cd.get("chapter_title")
            if title and title not in chapter_set:
                chapter_set.append(title)
    chapter_set = sorted(chapter_set, key=natural_sort_key)
    return {"chapters": chapter_set}
    
@router.get("/chapter-status", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "read"))])
async def get_chapter_status(
    board: str,
    standard: str,
    state: str,
    subject: str,
    chapter_title: str,
    publication_year: Optional[str] = None,
    textbook_name: Optional[str] = None
):
    """Check the processing status of a specific chapter."""
    query = {
        "board": board,
        "standard": standard,
        "state": state,
        "subject": subject,
        "chapter_title": chapter_title
    }
    
    if publication_year:
        query["publication_year"] = publication_year

    if textbook_name and textbook_name.strip() and textbook_name.strip().lower() != "null":
        query["textbook_name"] = textbook_name.strip()
    else:
        query["textbook_name"] = None
        
    status_doc = await db.chapter_status.find_one(query)
    
    if not status_doc:
        return {"status": "not_found"}
        
    return {
        "status": status_doc.get("status"),
        "error": status_doc.get("error"),
        "progress": status_doc.get("progress", 0),
        "updated_at": status_doc.get("updated_at")
    }

# --------------------------
# ROUTES - TEXTBOOK & CHAPTER MANAGEMENT
# --------------------------

@router.get("/textbooks", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "read"))])
async def get_all_textbooks():
    """Fetch all uploaded textbooks and their generated chapters."""
    textbooks = await db.textbook.find({}).sort("created_at", -1).to_list(None)
    for t in textbooks:
        t["_id"] = str(t["_id"])
        if isinstance(t.get("chapters"), list):
            t["chapters"] = sorted(t["chapters"], key=natural_sort_key)
    return {"textbooks": textbooks}

@router.put("/textbook/{textbook_id}")
async def update_textbook(textbook_id: str, request: Request, current_admin: dict = Depends(require_permission("Exams, Textbooks & Syllabus", "update"))):
    """Edit textbook metadata and cascade updates."""
    data = await request.json()
    textbook = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
    if not textbook:
        raise HTTPException(status_code=404, detail="Textbook not found")
        
    update_data = {}
    for key in ["board", "standard", "state", "subject", "category", "publication_year", "textbook_name"]:
        if key in data:
            val = data[key].strip() if isinstance(data[key], str) else data[key]
            if val and str(val).lower() != "null":
                update_data[key] = val
            else:
                update_data[key] = None
                
    if update_data:
        # Update textbook
        await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": update_data})
        
        # Update textbook_chapters
        await db.textbook_chapters.update_many(
            {"textbook_id": str(textbook_id)}, 
            {"$set": update_data}
        )
        
        # Update chapter_status using old metadata signature
        old_query = {
            "board": textbook.get("board"),
            "standard": textbook.get("standard"),
            "state": textbook.get("state"),
            "subject": textbook.get("subject"),
            "publication_year": textbook.get("publication_year"),
            "textbook_name": textbook.get("textbook_name")
        }
        await db.chapter_status.update_many(old_query, {"$set": update_data})
        
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "edit_textbook",
            f"Updated textbook {textbook_id} metadata",
            status="success"
        )
        
    return {"status": "success", "message": "Textbook updated successfully"}

@router.delete("/textbook/{textbook_id}/chapter/{chapter_name}", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "delete"))])
async def delete_textbook_chapter(textbook_id: str, chapter_name: str):
    """Delete a specific chapter and all its extracted passages and status from a textbook."""
    textbook = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
    if not textbook:
        raise HTTPException(status_code=404, detail="Textbook not found")
        
    # Delete passages and vectors from textbook_chapters collection
    del_result = await db.textbook_chapters.delete_many({
        "$or": [
            {"textbook_id": str(textbook_id), "chapter_title": chapter_name},
            {
                "board": textbook.get("board"),
                "standard": str(textbook.get("standard")),
                "subject": textbook.get("subject"),
                "chapter_title": chapter_name
            }
        ]
    })

    # Delete chapter processing status
    await db.chapter_status.delete_many({
        "$or": [
            {"textbook_id": str(textbook_id), "chapter_title": chapter_name},
            {
                "board": textbook.get("board"),
                "standard": str(textbook.get("standard")),
                "subject": textbook.get("subject"),
                "chapter_title": chapter_name
            }
        ]
    })

    # Remove chapter from the textbook's chapter list
    await db.textbook.update_one(
        {"_id": ObjectId(textbook_id)},
        {"$pull": {"chapters": chapter_name}}
    )
    
    return {
        "status": "success", 
        "message": f"Deleted chapter '{chapter_name}' and its extracted content successfully",
        "deleted_passages_count": del_result.deleted_count
    }

@router.delete("/textbook/{textbook_id}", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "delete"))])
async def delete_textbook(textbook_id: str):
    """Delete an entire textbook and all its associated extracted chapters, passages, vectors, and status."""
    textbook = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
    if not textbook:
        raise HTTPException(status_code=404, detail="Textbook not found")
        
    # Delete all extracted passages and vectors from db.textbook_chapters
    del_result = await db.textbook_chapters.delete_many({
        "$or": [
            {"textbook_id": str(textbook_id)},
            {
                "board": textbook.get("board"),
                "standard": str(textbook.get("standard")),
                "state": textbook.get("state"),
                "subject": textbook.get("subject")
            }
        ]
    })

    # Delete all chapter processing status entries
    await db.chapter_status.delete_many({
        "$or": [
            {"textbook_id": str(textbook_id)},
            {
                "board": textbook.get("board"),
                "standard": str(textbook.get("standard")),
                "state": textbook.get("state"),
                "subject": textbook.get("subject")
            }
        ]
    })

    # Delete extracted syllabus entries for this board/standard/subject
    await db.syllabus.delete_many({
        "board": textbook.get("board"),
        "standard": str(textbook.get("standard")),
        "subject": textbook.get("subject")
    })

    # Delete the main textbook document
    await db.textbook.delete_one({"_id": ObjectId(textbook_id)})
    
    return {
        "status": "success", 
        "message": f"Deleted textbook '{textbook_id}' and all extracted content successfully",
        "deleted_passages_count": del_result.deleted_count
    }

# --------------------------
# ROUTES - QUESTION GENERATION
# --------------------------

@router.post("/generate-questions")
async def generate_questions_trigger(
    payload: dict = Body(...),
    current_admin: dict = Depends(require_permission("Exams, Textbooks & Syllabus", "create"))
):
    try:
        standard = payload.get("standard")
        subject = payload.get("subject")
        chapters = payload.get("chapters", [])
        # Align with question_generation.html payload keys: paper_count, total_marks
        papers = int(payload.get("paper_count") or payload.get("papers") or 1)
        marks = int(payload.get("total_marks") or payload.get("marks") or payload.get("TotalMarks") or 50)
        time_limit = payload.get("time_limit") or payload.get("time")

        if not standard or not subject or not chapters:
            raise HTTPException(status_code=400, detail="standard, subject and chapters are required")

        # task_id = str(uuid.uuid4())  <-- REMOVED
        task_doc = {
            # "task_id": task_id,      <-- REMOVED
            "standard": standard,
            "subject": subject,
            "chapters": chapters,
            "papers": papers,
            "marks": marks,
            "time_limit": time_limit, # Save user's selected time
            "status": "queued",
            "progress": 0,
            "created_at": datetime.now(timezone.utc)
        }
        result = await db.question_tasks.insert_one(task_doc)
        task_oid = str(result.inserted_id)

        activity_log = await db.admin_activity_logs.insert_one({
            "username": current_admin["sub"],
            "role": current_admin["role"],
            "action": "generate_questions",
            "status": "processing",
            "details": f"Generating {papers} question paper(s) of {marks} marks for Class {standard} {subject}",
            "task_id": task_oid,
            "timestamp": datetime.now(timezone.utc)
        })

        asyncio.create_task(generate_questions_worker(task_oid, str(activity_log.inserted_id)))
        return {"status": "started", "task_id": task_oid}
    except HTTPException as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "generate_questions",
            f"Failed to generate questions for Class {payload.get('standard')} {payload.get('subject')}: {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "generate_questions",
            f"Failed to generate questions for Class {payload.get('standard')} {payload.get('subject')}: {exc}",
            status="failed",
        )
        raise



async def generate_questions_worker(task_id: str, activity_log_id: str | None = None):
    # Query using _id
    task = await db.question_tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        return

    await db.question_tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": "running", "progress": 5}}
    )

    std = int(task["standard"])
    total_marks = int(task["marks"])
    chapters = task["chapters"]
    subject = task["subject"]
    papers = task["papers"]

    allowed_types, sections = get_exam_structure(std, total_marks)
    generated_ids = []

    # --- RAG: Fetch Chapter Content ---
    print(f"[BG-GEN] Step 1: Fetching chapter content from database (RAG)...")
    chapter_docs = await db.textbook_chapters.find({
        "standard": str(std),
        "subject": subject,
        "chapter_title": {"$in": chapters}
    }).sort("passage_index", 1).to_list(None)

    # Determine overall language based on Subject (Hindi -> hi, Malayalam -> ml, Others -> en)
    majority_lang = determine_language_from_subject(subject)
    print(f"[BG-GEN] Subject '{subject}' -> Determined overall generation language: '{majority_lang}'")

    # Group passages by chapter title
    chapter_content_map = {}
    for doc in chapter_docs:
        title = doc.get("chapter_title")
        content = doc.get("content", "")
        vector = doc.get("vector", [])
        if title not in chapter_content_map:
            chapter_content_map[title] = []
        # Store both content and vector
        chapter_content_map[title].append({"content": content, "vector": vector})

    # Helper for Python-based Cosine Similarity
    import numpy as np
    def cosine_similarity(v1, v2):
        if not v1 or not v2: return 0.0
        return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

    used_questions = []  # Accumulate all questions used across papers to avoid repetition

    try:
        for p in range(papers):
            section_text = "\n".join([f"Section {key}: {val[0]} mark questions × {val[1]}" for key, val in sections.items()])

            # Build the exclusion block — grows with each paper generated
            if used_questions:
                exclusion_block = (
                    "\n### PREVIOUSLY USED QUESTIONS (DO NOT REPEAT OR REPHRASE ANY OF THESE) ###\n"
                    + "\n".join(f"- {q}" for q in used_questions)
                    + "\n### END EXCLUSION LIST ###\n"
                    + "\nIMPORTANT: Every question in this paper MUST be completely different in both topic angle and phrasing from the above list.\n"
                )
            else:
                exclusion_block = ""
                
            # --- ITERATIVE CONCEPT EXHAUSTION (DYNAMIC SEMANTIC SEARCH) ---
            context_text = ""
            for title, passages_data in chapter_content_map.items():
                total_passages = len(passages_data)
                
                if total_passages <= 10:
                    selected_passages_texts = [p["content"] for p in passages_data]
                    strategy = "ALL_PASSAGES (Short Chapter)"
                else:
                    strategy = f"SEMANTIC_SEARCH_TOP_10_ITERATION_{p+1}"
                    # Evolve the query based on the paper index
                    if p == 0:
                        synthetic_query = f"Core concepts, important definitions, main historical events, standard formulas, and comprehensive summary of chapter: {title}"
                    elif p == 1:
                        synthetic_query = f"Secondary topics, nuanced edge cases, minor definitions, and application examples of chapter: {title}"
                    else:
                        synthetic_query = f"Obscure facts, deep corners, minor historical figures, complex tricky application examples, and rarely tested areas of chapter: {title}"
                        
                    try:
                        emb_res = await client.embeddings.create(model="text-embedding-3-large", input=synthetic_query)
                        query_vector = emb_res.data[0].embedding
                        if hasattr(emb_res, 'usage') and emb_res.usage:
                            from app.utils.ai_usage_logger import log_ai_usage
                            await log_ai_usage("ADMIN", "Question Gen - Context Search", "text-embedding-3-large", emb_res.usage)
                        
                        scored_passages = []
                        for passage in passages_data:
                            score = cosine_similarity(query_vector, passage["vector"])
                            scored_passages.append((score, passage["content"]))
                            
                        scored_passages.sort(key=lambda x: x[0], reverse=True)
                        selected_passages_texts = [content for score, content in scored_passages[:10]]
                    except Exception as e:
                        print(f"[DEBUG] Semantic Search Failed for {title}, iteration {p+1}: {e}")
                        step = max(1, total_passages // 10)
                        selected_passages_texts = [psg["content"] for psg in passages_data[::step][:10]]
                        strategy = f"FALLBACK_UNIFORM_SAMPLING_LIMIT_10"
                
                print(f"[DEBUG] Paper {p+1} - Strategy: {strategy} for chapter: {title}")
                chapter_text = "\n".join(selected_passages_texts)
                context_text += f"\n=== CHAPTER: {title} ===\n{chapter_text}\n"

            # Extract board (SCERT/NCERT) if available, defaulting to SCERT
            board = task.get("board") or (chapter_docs[0].get("board") if chapter_docs else None) or "SCERT"

            # Prepare dynamic sections JSON block for the prompt
            sections_list = []
            for name, val in sections.items():
                sections_list.append(f'{{"section": "{name}", "marks_per_question": {val[0]}, "questions": []}}')
            sections_json_block = ",\n    ".join(sections_list)

            # Determine Peer/Pedagogy Prompt based on Standard
            print(f"[BG-GEN] Step 2: Generating Paper {p+1} via OpenAI ({'Vision/Primary' if std <= 5 else 'Standard'} mode, Language: {majority_lang}, Board: {board})...")
            
            lang_instruction = ""
            if majority_lang == "ml":
                lang_instruction = """പരീക്ഷാ ചോദ്യപേപ്പർ തയ്യാറാക്കുന്നതിൽ ഉയർന്ന പരിചയമുള്ള ഒരു മലയാളം അധ്യാപകനായി പ്രവർത്തിക്കുക:
- ചോദ്യങ്ങളും ഓപ്ഷനുകളും ഉത്തരങ്ങളും പൂർണ്ണമായും സ്വാഭാവികവും വ്യാകരണപരമായി ശരിയുമായ മലയാളത്തിൽ എഴുതുക.
- നൽകിയിരിക്കുന്ന പാഠഭാഗത്തെ (Textbook Content) അടിസ്ഥാനമാക്കി മാത്രമേ ചോദ്യങ്ങൾ നിർമ്മിക്കാവൂ.
- അനാവശ്യമായ ഇംഗ്ലീഷ് വാക്കുകളോ അപൂർണ്ണമായ വാക്യങ്ങളോ ഒഴിവാക്കുക."""
            elif majority_lang == "hi":
                lang_instruction = """परीक्षा के लिए एक पेशेवर प्रश्नपत्र निर्माता के रूप में कार्य करें:
- सभी प्रश्नों, विकल्पों और उत्तरों को विशुद्ध एवं व्याकरणिक रूप से सही हिन्दी में लिखें।
- केवल प्रदान किए गए पाठ से ही प्रश्न बनाएँ।
- अंग्रेजी शब्दों का प्रयोग न करें।"""
            else:
                lang_instruction = """Follow English language rules:
- All questions, options, and answers must be in clean, grammatically accurate English based strictly on the textbook content."""

            prompt = f"""You are an experienced school teacher and professional question-paper setter.

Your task is to generate a high-quality question paper for the specified BOARD/CURRICULUM, CLASS, SUBJECT, CHAPTERS, and TOTAL MARKS.

### EXAM DETAILS

Board/Curriculum: {board}
Class/Standard: {std}
Subject: {subject}
Selected Chapters: {', '.join(chapters)}
Total Marks: {total_marks}
Paper Number: {p + 1} of {papers}

### LANGUAGE REQUIREMENT
{lang_instruction}

### IMPORTANT CURRICULUM RULE

The student follows the specified curriculum: {board}.

- If Board/Curriculum is NCERT, generate questions strictly from the supplied NCERT textbook content.
- If Board/Curriculum is SCERT, generate questions strictly from the supplied SCERT textbook content.
- NEVER mix NCERT and SCERT content.
- Do not use content from another board, curriculum, class, or textbook.
- The supplied textbook content is the PRIMARY and AUTHORITATIVE source for question generation.
- Do not invent facts, definitions, formulas, examples, characters, events, terminology, diagrams, or concepts that are not supported by the supplied textbook content.
- Use the terminology and concepts appropriate to the supplied textbook.
- Questions must be appropriate for the specified class.

### CLASS-BASED LEVEL

Classes 1–5:
Generate age-appropriate questions focusing on recognition, recall, basic understanding, simple application, activities, pictures, and simple reasoning.

Classes 6–8:
Generate questions focusing on knowledge, understanding, application, reasoning, problem solving, interpretation, and age-appropriate higher-order thinking.

Classes 9–10:
Generate questions focusing on conceptual understanding, application, analysis, problem solving, interpretation, reasoning, and examination-level thinking.

Classes 11–12:
Generate questions focusing on advanced conceptual understanding, application, analysis, evaluation, problem solving, derivation/calculation where applicable, interpretation, and subject-specific higher-order thinking.

### QUESTION PAPER STRUCTURE

Follow the exact section structure supplied by the system.

For every section:
- Use exactly the specified number of questions.
- Use exactly the specified marks per question.
- Do not add extra questions.
- Do not remove questions.
- Do not change the marks.
- Do not merge sections.
- Do not create additional sections.

The total marks of the generated paper MUST exactly equal {total_marks}.

### DIFFICULTY PROGRESSION

Section A:
- Basic knowledge
- Recall
- Recognition
- Direct understanding
- Simple calculation where appropriate

Section B:
- Understanding
- Short explanation
- Simple application
- One or two logical steps

Section C:
- Application
- Reasoning
- Problem solving
- Interpretation
- Multiple logical steps

Section D/E:
- Higher-order thinking
- Analysis
- Complex application
- Interpretation
- Multi-step reasoning
- Problem solving
- Evaluation where appropriate

IMPORTANT:
Higher-mark questions must be more intellectually demanding, not simply longer.
Do not make a question difficult merely by adding unnecessary words.

### SUBJECT-SPECIFIC RULES

MATHEMATICS:
Use appropriate questions involving calculations, mathematical concepts, algebra, geometry, mensuration, graphs, tables, construction, verification/proof where applicable, real-life applications, reasoning, multi-step problem solving.

SCIENCE:
Use appropriate questions involving definitions, concepts, explanations, reasons, comparisons, classification, experiments, observations, diagrams when supported by textbook, applications, case/context-based questions, scientific reasoning.

SOCIAL SCIENCE:
Use appropriate questions involving facts/concepts, events, processes, causes/effects, comparisons, maps when supported by textbook, source/context-based questions, interpretation, analytical reasoning, application.

ENGLISH:
Use appropriate questions involving reading comprehension, grammar, vocabulary, literature, text-based questions, short answers, explanation, writing, application, interpretation, higher-order comprehension.

MALAYALAM:
Use prescribed textbook content involving ആശയഗ്രഹണം, പദപ്രയോഗം, വ്യാകരണം, കവിത/ഗദ്യ comprehension, Context-based questions, Explanation, Literary analysis, Application.

HINDI:
Use prescribed textbook content involving पाठ comprehension, व्याकरण, शब्दावली, गद्य/पद्य comprehension, संदर्भ आधारित प्रश्न, Explanation, Application.

For any other subject:
Use question types and cognitive levels appropriate to the subject, class, and supplied textbook content.

### QUESTION TYPE

Do NOT force every question to be an MCQ. Choose the most appropriate question type based on Subject, Class, Section, Marks, Learning objective, and Textbook content.
Allowed Question Types for this paper: {allowed_types}

### QUESTION QUALITY

Every question MUST:
1. Be grammatically correct, clear, and unambiguous.
2. Be complete and self-contained with a clear expected answer.
3. Match the allocated marks and student's class level.
4. Test a meaningful concept using correct textbook terminology.
5. Avoid unnecessary complexity, repeated questions, or reworded versions of another question.
6. Avoid invented facts, concepts, or unrelated information.

### CHAPTER COVERAGE

Distribute questions appropriately across ALL selected chapters: {', '.join(chapters)}. Do not generate most questions from only one chapter.

### VISUAL QUESTIONS

Use pictures, diagrams, graphs, tables, maps, or other visual questions ONLY when the required visual information is actually available in the supplied textbook content.
NEVER write "Look at the picture below" or "Observe the graph below" unless that visual is provided. If unavailable, convert into a clear text-based equivalent.

### MARKING DEPTH

1 mark: Direct answer, recall, identification, simple calculation, one-step response.
2 marks: Short explanation, simple application, approximately two logical steps.
3 marks: Application, reasoning, calculation, multiple logical steps, supporting reasoning.
4–5 marks: Detailed application, multi-step problem solving, analysis, interpretation, higher-order reasoning.

### MULTIPLE PAPERS

This is Paper {p + 1} of {papers}. Every paper must contain fresh, non-duplicate questions.
{exclusion_block}

### TEXTBOOK SOURCE MATERIAL

Use ONLY the following supplied textbook/RAG content:

{context_text}

### QUESTION TYPE JSON STRUCTURES ###
- MCQ: {{ "question": "...", "type": "MCQ", "options": ["A", "B", "C", "D"], "answer": "..." }}
- TRUEFALSE: {{ "question": "...", "type": "TRUEFALSE", "answer": "True" }}
- FILLINTHEBLANKS: {{ "question": "The ___ is blue.", "type": "FILLINTHEBLANKS", "answer": "sky" }}
- MATCHTHEFOLLOWING: {{ "question": "Match items", "type": "MATCHTHEFOLLOWING", "left": ["Cat", "Dog"], "right": ["Meow", "Bark"] }}
- PICTUREBASED: {{ "question": "What is in the picture?", "type": "PICTUREBASED", "answer": "..." }}
- VERYSHORT/SHORT/ESSAY: {{ "question": "...", "type": "SHORT", "answer": "..." }}

### REQUIRED SECTIONS & QUESTION COUNTS ###
{section_text}

### FINAL VALIDATION BEFORE OUTPUT

Before returning the paper, internally verify:
1. Correct board/curriculum: {board}
2. Correct class: {std}
3. Correct subject: {subject}
4. Only selected chapters are used.
5. No NCERT/SCERT content is mixed.
6. Every question is supported by the supplied textbook content.
7. Correct section count and marks per question matching the section blueprint exactly.
8. Correct total marks equal to {total_marks}.
9. Correct difficulty progression and no duplicate/rephrased questions.
10. JSON format is valid.

### OUTPUT FORMAT ###
Respond with valid JSON only. No text outside JSON.

{{
  "paper_id": "{task_id}-{p+1}",
  "standard": "{std}",
  "subject": "{subject}",
  "chapters_used": {json.dumps(chapters)},
  "sections": [
    {sections_json_block}
  ]
}}"""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2  # Higher temperature = more creative variation across papers
            )

            content = response.choices[0].message.content
            
            # Log usage
            if hasattr(response, 'usage') and response.usage:
                from app.utils.ai_usage_logger import log_ai_usage
                await log_ai_usage("ADMIN", "Question Generation", "gpt-4o-mini", response.usage)
            cleaned = content.replace("```json", "").replace("```", "").strip()

            try:
                paper_json = json.loads(cleaned)
            except Exception:
                paper_json = {"paper_id": f"{task_id}-{p+1}", "sections": []}

            if not isinstance(paper_json, dict):
                paper_json = {"paper_id": f"{task_id}-{p+1}", "sections": []}

            # Guarantee paper_id exists in paper_json
            paper_id_val = paper_json.get("paper_id") or f"{task_id}-{p+1}"
            paper_json["paper_id"] = paper_id_val

            # Collect all question texts from this paper to exclude from next papers
            for section in paper_json.get("sections", []):
                for q in section.get("questions", []):
                    # Defensive check: AI might return strings instead of objects
                    if isinstance(q, dict):
                        q_text = q.get("question") or q.get("text") or ""
                    else:
                        q_text = str(q)
                    
                    if q_text:
                        used_questions.append(q_text.strip())

            # --- PDF Generation ---
            print(f"[BG-GEN] Step 3: Rendering PDF for Paper {p+1}...")
            paper_json["marks"] = total_marks
            paper_json["standard"] = str(std)
            paper_json["subject"] = subject
            user_time = task.get("time_limit")
            if user_time:
                paper_json["time"] = f"TIME - {user_time} MINUTES" if str(user_time).isdigit() else str(user_time)
            else:
                paper_json["time"] = "TIME - 90 MINUTES" if total_marks >= 50 else "TIME - 45 MINUTES"

            paper_filename = f"{GENERATED_PDF_DIR}/{paper_id_val}.pdf"
            try:
                if std <= 5:
                    save_primary_question_paper(paper_json, paper_filename)
                else:
                    save_scert_question_paper(paper_json, paper_filename)
            except Exception as e:
                print(f"Failed to generate PDF for paper {paper_id_val}: {e}")

            # Insert JSON into DB with pdf_path included
            result = await db.generated_papers.insert_one({
                "task_id": task_id,
                "paper_index": p + 1,
                "paper": paper_json,
                "pdf_path": paper_filename,
                "created_at": datetime.utcnow(),
            })
            generated_ids.append(str(result.inserted_id))

            # Update progress
            await db.question_tasks.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": {"progress": int((p + 1) / papers * 100)}}
            )

    except Exception as e:
        err_str = str(e)
        print(f"CRITICAL: Question Generation Worker Failed for task {task_id}: {err_str}")

        # Classify the error into a friendly, human-readable message
        if "credit_balance_exhausted" in err_str or "insufficient_quota" in err_str:
            friendly_error = (
                "⚠️ OpenAI Credits Exhausted: Your OpenAI API account has no remaining credits. "
                "Please top up your balance at https://platform.openai.com/settings/organization/billing "
                "and then try generating again."
            )
        elif "invalid_api_key" in err_str or "Incorrect API key" in err_str:
            friendly_error = (
                "🔑 Invalid OpenAI API Key: The API key in your .env file is incorrect or has been revoked. "
                "Please set a valid OPENAI_API_KEY and restart the server."
            )
        elif "RateLimitError" in err_str or "rate_limit" in err_str:
            friendly_error = (
                "⏳ OpenAI Rate Limit Hit: Too many requests were sent in a short time. "
                "Please wait a few minutes and try generating again."
            )
        elif "Connection" in err_str or "timeout" in err_str.lower():
            friendly_error = (
                "🌐 Network Error: Could not reach the OpenAI API during question generation. "
                "Please check your internet connection and try again."
            )
        else:
            friendly_error = f"Question generation failed. Reason: {err_str}"

        await db.question_tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"status": "failed", "message": friendly_error}}
        )
        if activity_log_id:
            await db.admin_activity_logs.update_one(
                {"_id": ObjectId(activity_log_id)},
                {"$set": {"status": "failed", "details": f"Failed to generate questions for task {task_id}: {friendly_error}"}}
            )
        return

    # Mark job completed
    await db.question_tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": "completed", "generated": generated_ids}}
    )
    if activity_log_id:
        task = await db.question_tasks.find_one({"_id": ObjectId(task_id)})
        if task:
            await db.admin_activity_logs.update_one(
                {"_id": ObjectId(activity_log_id)},
                {"$set": {"status": "completed", "details": f"Generated {task.get('papers', 1)} question paper(s) of {task.get('marks', 0)} marks for Class {task.get('standard')} {task.get('subject')}"}}
            )

# --------------------------
# ROUTES - JOB STATUS / GENERATED PAPERS
# --------------------------

@router.get("/question-task-status/{task_id}", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "read"))])
async def question_task_status(task_id: str):
    task = await db.question_tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task_id,
        "status": task.get("status", "unknown"),
        "progress": task.get("progress", 0),
        "message": task.get("message", "")
    }
    

def _ensure_pdf_exists(paper_doc: dict, force_rerender: bool = False) -> Optional[str]:
    """
    Checks if PDF file exists on disk in app/static/generated_papers for a paper record;
    if missing, mislocated, or force_rerender is True, re-renders PDF on the fly from stored JSON.
    Returns static PDF URL (e.g. /generated_papers/xxx.pdf) or None.
    """
    paper_info = paper_doc.get("paper") or {}
    if not isinstance(paper_info, dict):
        return None

    paper_id_code = paper_info.get("paper_id") or str(paper_doc.get("_id", "paper"))
    paper_info["paper_id"] = paper_id_code

    filename = f"{paper_id_code}.pdf"
    canonical_pdf_path = os.path.join(GENERATED_PDF_DIR, filename)

    # 1. Check if canonical PDF exists; if missing check legacy/alternate path and copy
    if not force_rerender and not os.path.exists(canonical_pdf_path):
        old_pdf_path = paper_doc.get("pdf_path")
        if old_pdf_path and os.path.exists(old_pdf_path) and os.path.abspath(old_pdf_path) != os.path.abspath(canonical_pdf_path):
            try:
                import shutil
                shutil.copy2(old_pdf_path, canonical_pdf_path)
            except Exception as e:
                print(f"[AUTO-HEAL-PDF] Could not copy from {old_pdf_path}: {e}")

    # 2. If missing or force_rerender is True, re-render PDF on the fly from paper_info JSON
    if (force_rerender or not os.path.exists(canonical_pdf_path)) and paper_info:
        try:
            raw_std = paper_info.get("standard") or paper_doc.get("standard") or 1
            try:
                std = int(raw_std)
            except (ValueError, TypeError):
                std = 1

            paper_info["standard"] = str(std)
            if "subject" not in paper_info or not paper_info["subject"]:
                paper_info["subject"] = paper_doc.get("subject") or "General"
            if "marks" not in paper_info or not paper_info["marks"]:
                paper_info["marks"] = paper_doc.get("marks") or 50

            if std <= 5:
                save_primary_question_paper(paper_info, canonical_pdf_path)
            else:
                save_scert_question_paper(paper_info, canonical_pdf_path)
        except Exception as e:
            print(f"[AUTO-HEAL-PDF] Failed to re-render PDF on the fly for {paper_id_code}: {e}")

    if os.path.exists(canonical_pdf_path):
        mtime = int(os.path.getmtime(canonical_pdf_path))
        return f"/generated_papers/{filename}?v={mtime}"
    return None


@router.get("/generated-papers")
async def get_generated_papers(task_id: Optional[str] = None):
    q = {}
    if task_id and task_id != "undefined":
        q["task_id"] = task_id
    docs = await db.generated_papers.find(q).sort([("created_at", -1), ("_id", -1)]).to_list(None)
    for d in docs:
        d["_id"] = str(d["_id"])
        paper_info = d.get("paper", {})
        pdf_url = _ensure_pdf_exists(d, force_rerender=True)

        d["pdf_url"] = pdf_url
        d["download_url"] = pdf_url

        std = paper_info.get("standard") or d.get("standard", "N/A")
        sub = paper_info.get("subject") or d.get("subject", "N/A")
        chaps = paper_info.get("chapters_used", []) or d.get("chapters", [])
        chap_str = chaps[0] if chaps else "N/A"
        if len(chaps) > 1:
            chap_str += f" +{len(chaps)-1} more"

        d["filename"] = f"Class {std} {sub} - {chap_str}"
    return docs


@router.delete("/generated-paper/{paper_id}", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "delete"))])
async def delete_generated_paper(paper_id: str):
    doc = await db.generated_papers.find_one({"_id": ObjectId(paper_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Delete PDF file from folder
    pdf_path = doc.get("pdf_path")
    if pdf_path and os.path.exists(pdf_path):
        os.remove(pdf_path)

    await db.generated_papers.delete_one({"_id": ObjectId(paper_id)})

    return {"status": "deleted", "message": "Question paper removed successfully"}


@router.get("/generated-papers/filter", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "read"))])
async def get_generated_papers_filter(standard: str, subject: str):
    docs = await db.generated_papers.find(
        {"$or": [{"paper.standard": str(standard), "paper.subject": subject}, {"standard": str(standard), "subject": str(subject)}]}
    ).sort([("created_at", -1), ("_id", -1)]).to_list(None)

    for d in docs:
        d["_id"] = str(d["_id"])
        paper_info = d.get("paper", {})
        pdf_url = _ensure_pdf_exists(d, force_rerender=True)

        d["pdf_url"] = pdf_url
        d["download_url"] = pdf_url

        std = paper_info.get("standard") or d.get("standard", standard)
        sub = paper_info.get("subject") or d.get("subject", subject)
        chaps = paper_info.get("chapters_used", []) or d.get("chapters", [])
        chap_str = chaps[0] if chaps else "N/A"
        if len(chaps) > 1:
            chap_str += f" +{len(chaps)-1} more"

        d["filename"] = f"Class {std} {sub} - {chap_str}"

    return docs

