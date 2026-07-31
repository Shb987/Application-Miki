
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

EXAM_STRUCTURES = {
    1: (["MCQ", "FillInTheBlanks", "MatchTheFollowing", "TrueFalse", "PictureBased"],  {"A": (1, 25)}),
    2: (["MCQ", "FillInTheBlanks", "MatchTheFollowing", "TrueFalse", "PictureBased", "VeryShort"], {"A": (1, 15), "B": (2, 5)}),
    3: (["MCQ", "FillInTheBlanks", "MatchTheFollowing", "TrueFalse", "PictureBased", "VeryShort"], {"A": (1, 15), "B": (2, 5)}),
    4: (["MCQ", "FillInTheBlanks", "TrueFalse", "VeryShort", "Short"], {"A": (1, 10), "B": (2, 5), "C": (3, 2)}),
    5: (["MCQ", "FillInTheBlanks", "TrueFalse", "VeryShort", "Short", "PictureBased"], {"A": (1, 15), "B": (2, 5), "C": (4, 2)}),
    6: (["MCQ", "VeryShort", "Short"], {"A": (1, 10), "B": (2, 5), "C": (4, 2)}),
    7: (["MCQ", "VeryShort", "Short", "ShortEssay"], {"A": (1, 10), "B": (2, 9), "C": (3, 4), "D": (5, 2)}),
    8: (["MCQ", "VeryShort", "Short", "ShortEssay"], {"A": (1, 10), "B": (2, 9), "C": (3, 4), "D": (5, 2)}),
}

HIGH_SCHOOL = {
    50:  (["MCQ", "VeryShort", "Short", "Essay", "Apply", "Analyze"], {"A": (1, 5), "B": (2, 5), "C": (3, 3), "D": (8, 2), "E": (10, 1)}),
    80: (["MCQ", "VeryShort", "Short", "Essay", "Apply", "Analyze"], {"A": (1, 10), "B": (2, 10), "C": (4, 4), "D": (5, 4), "E": (7, 2)}),
}

PLUS_TWO = {
    50:  (["MCQ", "Short", "Essay", "Apply", "Analyze", "CaseStudy", "Diagram"], {"A": (1, 5), "B": (3, 5), "C": (8, 3), "D": (10, 1)}),
    80: (["MCQ", "Short", "Essay", "Apply", "Analyze", "CaseStudy", "Diagram"], {"A": (1, 10), "B": (2, 10), "C": (3, 4), "D": (5, 4), "E": (9, 2)}),
}

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
    # Primary Standards (1-5) - Dynamic scaling
    if standard <= 5:
        types = ["MCQ", "FillInTheBlanks", "TrueFalse", "VeryShort", "PictureBased"]
        if standard >= 4: types.append("Short")
        
        # Proportional mapping: ~70% of marks to 1-mark questions, ~30% to 2-mark questions
        # Example for 25 marks: 15 questions (1 mark) + 5 questions (2 marks)
        # Example for 50 marks: 30 questions (1 mark) + 10 questions (2 marks)
        count_1 = int(total * 0.6)
        count_2 = int((total - count_1) / 2)
        # Add a section C for 3 marks if it's a big paper
        count_3 = 0
        if total >= 50:
            count_2 = 10
            count_1 = total - (count_2 * 2 + 5 * 3)
            count_3 = 5
            return (types, {"A": (1, count_1), "B": (2, count_2), "C": (3, count_3)})
            
        return (types, {"A": (1, count_1), "B": (2, count_2)})

    # Standards 6-8
    if standard <= 8:
        # For 6-8, we use a slightly more complex structure
        base_struct = EXAM_STRUCTURES.get(standard, EXAM_STRUCTURES[8])
        types, sec_map = base_struct
        # Scale A, B, C proportional to total marks (assuming base is for 50)
        scale = total / 50.0
        new_sec_map = {}
        for k, (v_mark, v_count) in sec_map.items():
            new_sec_map[k] = (v_mark, int(v_count * scale) if int(v_count * scale) > 0 else 1)
        return (types, new_sec_map)

    # High School (9-10)
    if standard in [9, 10]:
        return HIGH_SCHOOL.get(total, HIGH_SCHOOL[50])
        
    # Plus Two (11-12)
    return PLUS_TWO.get(total, PLUS_TWO[50])

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

async def extract_text_via_vision(file_path: str) -> str:
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


@router.post("/textbook/upload-batch", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "create"))])
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
    file: UploadFile = File(...)
):
    """
    Handle single chapter PDF upload. Immediately saves metadata and triggers
    background processing (extraction + embedding).
    """
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
        "subject": subject
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
    
    # 3. Queue Background Processing
    background_tasks.add_task(
        process_chapter_worker,
        textbook_query=textbook_query,
        full_chapter_title=full_chapter_title,
        file_path=file_path,
        original_filename=file.filename
    )

    return {
        "status": "processing",
        "message": f"Chapter '{full_chapter_title}' received. Processing started in background.",
    }

async def process_chapter_worker(textbook_query, full_chapter_title, file_path, original_filename):
    """Background worker to extract text and generate embeddings for a single chapter."""
    status_query = {
        "board": textbook_query.get("board"),
        "standard": textbook_query.get("standard"),
        "state": textbook_query.get("state"),
        "subject": textbook_query.get("subject"),
        "textbook_name": textbook_query.get("textbook_name"),
        "chapter_title": full_chapter_title
    }
    try:
        print(f"[BG-CHAPTER] Processing: {full_chapter_title} ({original_filename})")
        
        # 1. Extract Text
        print(f"[BG-CHAPTER] Step 1: Extracting text (File: {file_path})")
        text_content = ""
        
        # Branching: Use Vision for Standard 1-5 or as fallback
        standard_val = int(textbook_query.get("standard", 0))
        use_vision = standard_val > 0 and standard_val <= 5
        
        if use_vision:
            print(f"[BG-CHAPTER] Standard {standard_val} detected. Using VISION-BASED extraction for better quality.")
            text_content = await extract_text_via_vision(file_path)
        else:
            print(f"[BG-CHAPTER] Using standard text extraction (pdfplumber)...")
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    # Filter fragmented lines
                    lines = page_text.split('\n')
                    cleaned_lines = [l.strip() for l in lines if l.strip() and not (len(l.strip()) < 3 and l.strip().isdigit())]
                    text_content += "\n".join(cleaned_lines) + "\n"
            
            text_content = normalize_text(text_content)
            
            if not text_content.strip():
                print(f"[BG-CHAPTER] pdfplumber extracted NO text. Falling back to VISION-BASED extraction...")
                text_content = await extract_text_via_vision(file_path)

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
        PASSAGE_SIZE = 4000
        PASSAGE_OVERLAP = 400
        passages = []
        
        if len(text_content) <= PASSAGE_SIZE:
            passages.append(text_content)
        else:
            for i in range(0, len(text_content), PASSAGE_SIZE - PASSAGE_OVERLAP):
                passages.append(text_content[i:i + PASSAGE_SIZE])

        valid_docs = []
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key == "sk-placeholder":
            print("[BG-CHAPTER] WARNING: OPENAI_API_KEY is not set in .env file. Skipping embedding generation. Set OPENAI_API_KEY in .env to enable vector search.")
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
                        "chapter_title": full_chapter_title,
                        "content": passage.strip(),
                        "passage_index": p_idx,
                        "vector": vector,
                        "detected_language": detected_language,
                        "created_at": datetime.now(timezone.utc),
                    })
                except Exception as e:
                    print(f"[BG-CHAPTER] Embedding error [P{p_idx}]: {e}")

        if valid_docs:
            # Atomic update: clear old and insert new
            await db.textbook_chapters.delete_many({
                "textbook_id": textbook_id,
                "chapter_title": full_chapter_title
            })
            await db.textbook_chapters.insert_many(valid_docs)
            await db.chapter_status.update_one(
                status_query,
                {"$set": {"status": "completed", "updated_at": datetime.now(timezone.utc)}}
            )
            print(f"[BG-CHAPTER] SUCCESS: '{full_chapter_title}' processed with {len(valid_docs)} passages.")

    except Exception as e:
        print(f"[BG-CHAPTER] CRITICAL WORKER ERROR: {e}")
        await db.chapter_status.update_one(
            status_query,
            {"$set": {"status": "failed", "error": str(e), "updated_at": datetime.now(timezone.utc)}}
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

@router.delete("/textbook/{textbook_id}/chapter/{chapter_name}", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "delete"))])
async def delete_textbook_chapter(textbook_id: str, chapter_name: str):
    """Delete a specific chapter and its passages from a textbook."""
    textbook = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
    if not textbook:
        raise HTTPException(status_code=404, detail="Textbook not found")
        
    # Delete passages from vector db
    del_result = await db.textbook_chapters.delete_many({
        "textbook_id": textbook_id,
        "chapter_title": chapter_name
    })

    # Remove chapter from the textbook's chapter list
    await db.textbook.update_one(
        {"_id": ObjectId(textbook_id)},
        {"$pull": {"chapters": chapter_name}}
    )
    
    return {
        "status": "success", 
        "message": f"Deleted chapter '{chapter_name}' successfully",
        "deleted_passages_count": del_result.deleted_count
    }

@router.delete("/textbook/{textbook_id}", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "delete"))])
async def delete_textbook(textbook_id: str):
    """Delete an entire textbook and all its associated chapters and passages."""
    textbook = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
    if not textbook:
        raise HTTPException(status_code=404, detail="Textbook not found")
        
    # Delete passages from vector db
    del_result = await db.textbook_chapters.delete_many({
        "textbook_id": textbook_id
    })

    # Delete chapter statuses
    await db.chapter_status.delete_many({
        "board": textbook.get("board"),
        "standard": textbook.get("standard"),
        "state": textbook.get("state"),
        "subject": textbook.get("subject"),
        "textbook_name": textbook.get("textbook_name")
    })

    # Delete the textbook document
    await db.textbook.delete_one({"_id": ObjectId(textbook_id)})
    
    return {
        "status": "success", 
        "message": f"Deleted textbook '{textbook_id}' successfully",
        "deleted_passages_count": del_result.deleted_count
    }

# --------------------------
# ROUTES - QUESTION GENERATION
# --------------------------

@router.post("/generate-questions", dependencies=[Depends(require_permission("Exams, Textbooks & Syllabus", "create"))])
async def generate_questions_trigger(payload: dict = Body(...)):
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

    asyncio.create_task(generate_questions_worker(task_oid))
    return {"status": "started", "task_id": task_oid}



async def generate_questions_worker(task_id: str):
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

            # Prepare dynamic sections JSON block for the prompt
            sections_list = []
            for name, val in sections.items():
                sections_list.append(f'{{"section": "{name}", "marks_per_question": {val[0]}, "questions": []}}')
            sections_json_block = ",\n    ".join(sections_list)

            # Determine Peer/Pedagogy Prompt based on Standard
            print(f"[BG-GEN] Step 2: Generating Paper {p+1} via OpenAI ({'Vision/Primary' if std <= 5 else 'Standard'} mode, Language: {majority_lang})...")
            
            lang_instruction = ""
            if majority_lang == "ml":
                lang_instruction = """ നിങ്ങൾ കേരള SCERT പരീക്ഷാ ചോദ്യപേപ്പർ തയ്യാറാക്കുന്നതിൽ വലിയ പരിചയമുള്ള ഒരു മലയാളം അധ്യാപകനാണ്.

വളരെ പ്രധാനപ്പെട്ട നിയമങ്ങൾ:
1. ചോദ്യങ്ങളും ഓപ്ഷനുകളും ഉത്തരങ്ങളും പൂർണ്ണമായും മലയാളത്തിൽ തന്നെ എഴുതുക.
2. നൽകിയിരിക്കുന്ന പാഠഭാഗത്തെ അടിസ്ഥാനമാക്കി മാത്രമേ ചോദ്യങ്ങൾ നിർമ്മിക്കാവൂ.
3. എല്ലാ വാക്യങ്ങളും പൂർണ്ണവും വ്യാകരണപരമായി തികച്ചും ശരിയുമായിരിക്കണം. വാക്യങ്ങൾ അപൂർണ്ണമായി (ഉദാഹരണത്തിന് 'സാംസ്കാരിക' എന്ന് മാത്രം പറഞ്ഞ്) അവസാനിപ്പിക്കരുത്.
4. വിവർത്തനം ചെയ്തതുപോലെയുള്ള കൃത്രിമമായ മലയാളം ഒഴിവാക്കുക. സ്വാഭാവികവും ലളിതവുമായ ശൈലി ഉപയോഗിക്കുക.
5. അക്ഷരത്തെറ്റുകളോ തെറ്റായ പദപ്രയോഗങ്ങളോ ഉണ്ടാകരുത്.
6. കേരള SCERT പരീക്ഷകളിൽ ചോദിക്കാറുള്ള നിലവാരമുള്ള ചോദ്യങ്ങൾ തയ്യാറാക്കുക.
7. ചോദ്യങ്ങളിൽ അനാവശ്യമായ ഇംഗ്ലീഷ് വാക്കുകളോ ഇംഗ്ലീഷ് വാക്യഘടനയോ ഉപയോഗിക്കരുത്. """

            elif majority_lang == "hi":
                lang_instruction = """ आप परीक्षा के लिए एक पेशेवर प्रश्नपत्र निर्माता हैं। कृपया सभी प्रश्नों, विकल्पों और उत्तरों को विशुद्ध हिन्दी में लिखें। 

नियम:
1. केवल प्रदान किए गए पाठ से ही प्रश्न बनाएँ।
2. व्याकरणिक रूप से सही और स्वाभाविक हिन्दी का प्रयोग करें।
3. केरल बोर्ड पैटर्न का पालन करें।
4. अंग्रेजी शब्दों का प्रयोग न करें।
5. सभी प्रश्न स्पष्ट और सटीक हों।
6. उत्तरों को भी हिन्दी में दें।
7. सुनिश्चित करें कि विकल्प प्रश्न का भाग न हों। """

            else:
                lang_instruction = """ You are an experienced SCERT question paper setter.

Generate a high-quality SCERT question paper.

Rules:
- Use only English.
- Questions must be grammatically correct.
- Use textbook terminology.
- Do not invent facts.
- Do not translate from another language. """
                
            system_role_content = f"You are a professional SCERT Exam Paper Generator. Output valid JSON only.\n\n{lang_instruction}"
            if std <= 5:
                system_role_content = f"{PRIMARY_PEDAGOGY_PROMPT}\n\n{lang_instruction}"

            prompt = f"""
{system_role_content}

Kerala SCERT Board Exam Question Paper Generator — Paper {p + 1} of {papers}

Standard: {std}
Subject: {subject}
Chapters: {', '.join(chapters)}

Allowed Question Types: {allowed_types}

### TEXTBOOK CONTENT (SOURCE MATERIAL) ###
Use the following content to generate relevant questions. Do NOT ask questions outside this scope if possible.
{context_text}
### END CONTENT ###
{exclusion_block}
### QUESTION STRUCTURE REQUIREMENTS ###
1. Generate questions STRICTLY grouped by sections.
2. Follow EXACT question counts specified below.
3. **CRITICAL**: Ensure questions are distributed EVENLY across all provided chapters/topics. Do not focus only on the first few pages. Cover the entire provided content.
4. **UNIQUENESS**: Since this is paper {p + 1} of {papers}, generate FRESH questions that approach different concepts, facts, and angles from the chapter content. Avoid redundant or trivially rephrased questions.

### QUESTION TYPE JSON STRUCTURES ###
- MCQ: {{ "question": "...", "type": "MCQ", "options": ["A", "B", "C", "D"], "answer": "..." }}
- TRUEFALSE: {{ "question": "...", "type": "TRUEFALSE", "answer": "True" }}
- FILLINTHEBLANKS: {{ "question": "The ___ is blue.", "type": "FILLINTHEBLANKS", "answer": "sky" }}
- MATCHTHEFOLLOWING: {{ "question": "Match items", "type": "MATCHTHEFOLLOWING", "left": ["Cat", "Dog"], "right": ["Meow", "Bark"] }}
- PICTUREBASED: {{ "question": "What is in the picture?", "type": "PICTUREBASED", "answer": "..." }}
- VERYSHORT/SHORT/ESSAY: {{ "question": "...", "type": "SHORT", "answer": "..." }}

{section_text}

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
}}
"""

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

            # Insert JSON into DB
            # We store 'task_id' (which is the task's ObjectId string) for linking
            result = await db.generated_papers.insert_one({
                "task_id": task_id,
                "paper_index": p + 1,
                "paper": paper_json,
                "created_at": datetime.utcnow(),
            })
            generated_ids.append(str(result.inserted_id))

            # --- PDF Generation ---
            print(f"[BG-GEN] Step 3: Rendering PDF for Paper {p+1}...")
            try:
                # Inject metadata for PDF header
                paper_json["marks"] = total_marks
                paper_json["standard"] = str(std)
                paper_json["subject"] = subject
                # Use provided time_limit if exists, else fallback to calculation
                user_time = task.get("time_limit")
                if user_time:
                    paper_json["time"] = f"TIME - {user_time} MINUTES" if str(user_time).isdigit() else str(user_time)
                else:
                    paper_json["time"] = "TIME - 90 MINUTES" if total_marks >= 50 else "TIME - 45 MINUTES"

                paper_filename = f"{GENERATED_PDF_DIR}/{paper_json['paper_id']}.pdf"
                
                # Use specialized layout for Standards 1-5
                if std <= 5:
                    save_primary_question_paper(paper_json, paper_filename)
                else:
                    save_scert_question_paper(paper_json, paper_filename)
                # Update DB with PDF path
                await db.generated_papers.update_one(
                    {"_id": result.inserted_id},
                    {"$set": {"pdf_path": paper_filename}}
                )
            except Exception as e:
                print(f"Failed to generate PDF for paper {paper_json.get('paper_id')}: {e}")

            # Update progress
            await db.question_tasks.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": {"progress": int((p + 1) / papers * 100)}}
            )

    except Exception as e:
        print(f"CRITICAL: Question Generation Worker Failed for task {task_id}: {e}")
        await db.question_tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"status": "failed", "message": str(e)}}
        )
        return

    # Mark job completed
    await db.question_tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": "completed", "generated": generated_ids}}
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
    

@router.get("/generated-papers")
async def get_generated_papers(task_id: Optional[str] = None):
    q = {}
    if task_id:
        q["task_id"] = task_id
    docs = await db.generated_papers.find(q).to_list(None)
    for d in docs:
        d["_id"] = str(d["_id"])
        # Add pdf_url if pdf_path exists
        if "pdf_path" in d:
            # Match the mount point in main.py: app.mount("/generated_papers", ...)
            pdf_filename = os.path.basename(d["pdf_path"])
            d["pdf_url"] = f"/generated_papers/{pdf_filename}"
            # Match frontend expectations in question_generation.html
            d["download_url"] = d["pdf_url"]
            
            # Create a user-friendly filename/title from the paper data
            paper_info = d.get("paper", {})
            std = paper_info.get("standard", "N/A")
            sub = paper_info.get("subject", "N/A")
            chaps = paper_info.get("chapters_used", [])
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
    docs = await db.generated_papers.find({"paper.standard": standard, "paper.subject": subject}).to_list(None)

    for d in docs:
        d["_id"] = str(d["_id"])
        if "pdf_path" in d:
            # Match the mount point in main.py: app.mount("/generated_papers", ...)
            filename = os.path.basename(d["pdf_path"])
            d["pdf_url"] = f"/generated_papers/{filename}"

    return docs

