from fastapi import APIRouter, UploadFile, File, Form, Body, HTTPException, Request, BackgroundTasks, Query, Depends
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from bson import ObjectId
import pdfplumber
import pymupdf
import uuid
import json
import os
import re
import asyncio
import base64
import numpy as np

from app.core.database import db
from app.utils.admin_auth import require_permission, log_admin_activity
from app.report.competitive_exam_pdf import save_competitive_exam_paper
from openai import AsyncOpenAI

# --------------------------
# CONFIGURATION & CONSTANTS
# --------------------------
router = APIRouter(tags=["Competitive Exams Module"])
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or "sk-placeholder")

UPLOAD_DIR = "app/static/textbook"
os.makedirs(UPLOAD_DIR, exist_ok=True)

GENERATED_PDF_DIR = "app/static/generated_papers"
os.makedirs(GENERATED_PDF_DIR, exist_ok=True)

# Purge unused competitive exams template files removed from navigation
for _unused_tmpl in [
    "app/templates/admin/template/competitive_exams/comp_dashboard.html",
    "app/templates/admin/template/competitive_exams/comp_categories.html",
    "app/templates/admin/template/competitive_exams/comp_textbooks.html",
    "app/templates/admin/template/competitive_exams/comp_chapters.html",
    "app/templates/admin/template/competitive_exams/comp_generated_papers.html",
    "app/templates/admin/template/competitive_exams/comp_exams.html"
]:
    if os.path.exists(_unused_tmpl):
        try:
            os.remove(_unused_tmpl)
            print(f"[CLEANUP] Deleted removed template file: {_unused_tmpl}")
        except Exception as _e:
            pass

DEFAULT_CATEGORIES = [
    {"category_name": "UPSC Civil Services", "description": "Union Public Service Commission examinations (IAS, IPS, IFS, Prelims, Mains)", "icon": "fa-university", "is_active": True},
    {"category_name": "Kerala PSC", "description": "Kerala Public Service Commission examinations (KAS, Degree Level, 10th/12th Level)", "icon": "fa-certificate", "is_active": True},
    {"category_name": "SSC", "description": "Staff Selection Commission examinations (CGL, CHSL, MTS, CPO)", "icon": "fa-id-card", "is_active": True},
    {"category_name": "Banking & Insurance", "description": "IBPS, SBI PO, Clerk, RBI Grade B, LIC AAO examinations", "icon": "fa-money", "is_active": True},
    {"category_name": "Railway Recruitment", "description": "RRB NTPC, Group D, ALP, JE examinations", "icon": "fa-train", "is_active": True},
    {"category_name": "Other State PSCs", "description": "TNPSC, APPSC, KPSC, MPSC, UPPSC and other State Public Service examinations", "icon": "fa-map", "is_active": True},
    {"category_name": "Defence Examinations", "description": "NDA, CDS, AFCAT, CAPF, Territorial Army", "icon": "fa-shield", "is_active": True},
    {"category_name": "Teaching & Eligibility", "description": "CTET, KTET, NET / SET, PRT, TGT, PGT examinations", "icon": "fa-graduation-cap", "is_active": True},
    {"category_name": "NEET / JEE & Entrance", "description": "Medical, Engineering, and Higher Education Entrance examinations", "icon": "fa-flask", "is_active": True},
    {"category_name": "Other Competitive Exams", "description": "General recruitment and skill-based competitive assessments", "icon": "fa-briefcase", "is_active": True}
]

DEFAULT_EXAMS = [
    {
        "category_name": "UPSC Civil Services",
        "exam_name": "UPSC Civil Services (Prelims GS Paper 1)",
        "conducting_authority": "UPSC",
        "exam_level": "National",
        "exam_year": str(datetime.now().year),
        "syllabus_version": "Latest",
        "subjects": ["Indian Polity", "History & Culture", "Geography", "Economy", "General Science", "Environment"],
        "language": "en",
        "pattern": {
            "total_marks": 200,
            "duration_minutes": 120,
            "total_questions": 100,
            "negative_marking": True,
            "negative_marking_penalty": 0.66,
            "negative_marking_rule_text": "0.66 mark deducted for each incorrect response",
            "question_types": ["Single Best Answer MCQ", "Statement-based MCQ"],
            "difficulty_distribution": {"easy": 25, "medium": 55, "hard": 20}
        },
        "instructions": "Each question carries 2 marks. One-third of marks assigned to each question deducted for wrong answer.",
        "is_active": True
    },
    {
        "category_name": "Kerala PSC",
        "exam_name": "Kerala PSC (KAS / Degree Level Prelims)",
        "conducting_authority": "Kerala PSC",
        "exam_level": "State",
        "exam_year": str(datetime.now().year),
        "syllabus_version": "Latest",
        "subjects": ["General Studies", "Kerala History & Geography", "Constitution of India", "Current Affairs"],
        "language": "en",
        "pattern": {
            "total_marks": 100,
            "duration_minutes": 75,
            "total_questions": 100,
            "negative_marking": True,
            "negative_marking_penalty": 0.33,
            "negative_marking_rule_text": "0.33 mark deducted for each incorrect response",
            "question_types": ["Single Best Answer MCQ"],
            "difficulty_distribution": {"easy": 30, "medium": 50, "hard": 20}
        },
        "instructions": "Each correct answer carries 1 mark. 0.33 mark deducted for each wrong answer.",
        "is_active": True
    },
    {
        "category_name": "SSC",
        "exam_name": "SSC CGL (Tier 1 General Studies)",
        "conducting_authority": "Staff Selection Commission",
        "exam_level": "National",
        "exam_year": str(datetime.now().year),
        "syllabus_version": "Latest",
        "subjects": ["General Awareness", "Science", "History & Polity", "Economics"],
        "language": "en",
        "pattern": {
            "total_marks": 50,
            "duration_minutes": 60,
            "total_questions": 25,
            "negative_marking": True,
            "negative_marking_penalty": 0.50,
            "negative_marking_rule_text": "0.50 mark deducted for each incorrect response",
            "question_types": ["Single Best Answer MCQ"],
            "difficulty_distribution": {"easy": 35, "medium": 45, "hard": 20}
        },
        "instructions": "Each question carries 2 marks. 0.50 mark negative marking per wrong response.",
        "is_active": True
    },
    {
        "category_name": "Banking & Insurance",
        "exam_name": "IBPS / SBI PO (Banking & Financial Awareness)",
        "conducting_authority": "IBPS",
        "exam_level": "National",
        "exam_year": str(datetime.now().year),
        "syllabus_version": "Latest",
        "subjects": ["Banking Awareness", "Economy", "Financial Concepts"],
        "language": "en",
        "pattern": {
            "total_marks": 50,
            "duration_minutes": 35,
            "total_questions": 40,
            "negative_marking": True,
            "negative_marking_penalty": 0.25,
            "negative_marking_rule_text": "0.25 mark deducted for each incorrect response",
            "question_types": ["Single Best Answer MCQ"],
            "difficulty_distribution": {"easy": 30, "medium": 50, "hard": 20}
        },
        "instructions": "Negative marking of 1/4th of mark assigned to each question.",
        "is_active": True
    },
    {
        "category_name": "Defence Examinations",
        "exam_name": "NDA / CDS (General Knowledge & Studies)",
        "conducting_authority": "UPSC",
        "exam_level": "National",
        "exam_year": str(datetime.now().year),
        "syllabus_version": "Latest",
        "subjects": ["General Science", "Indian History", "Geography", "Current Affairs"],
        "language": "en",
        "pattern": {
            "total_marks": 100,
            "duration_minutes": 120,
            "total_questions": 100,
            "negative_marking": True,
            "negative_marking_penalty": 0.33,
            "negative_marking_rule_text": "0.33 mark deducted for each incorrect response",
            "question_types": ["Single Best Answer MCQ"],
            "difficulty_distribution": {"easy": 30, "medium": 50, "hard": 20}
        },
        "instructions": "Standard negative penalty applies for all objective questions.",
        "is_active": True
    }
]

# --------------------------
# HELPER FUNCTIONS
# --------------------------
def cosine_similarity(v1, v2):
    if not v1 or not v2: return 0.0
    arr1, arr2 = np.array(v1), np.array(v2)
    norm1, norm2 = np.linalg.norm(arr1), np.linalg.norm(arr2)
    if norm1 == 0 or norm2 == 0: return 0.0
    return float(np.dot(arr1, arr2) / (norm1 * norm2))

def normalize_text(text: str) -> str:
    """Collapses spaced letters, clears PDF artifacts and deduplicates double characters."""
    if not text: return ""
    import unicodedata
    # Clean Latin diacritics
    normalized = unicodedata.normalize('NFD', text)
    text = "".join(c for c in normalized if not (0x0300 <= ord(c) <= 0x036F))
    text = unicodedata.normalize('NFC', text)

    # Collapse characters separated by spaces (G e n e t i c s -> Genetics)
    text = re.sub(r'(?<=\b[A-Za-z]) (?=[A-Za-z]\b)', '', text)
    # Handle numbers: "1 1" -> "11"
    text = re.sub(r'(\b\d)\s+(\d\b)', r'\1\2', text)
    # Handle doubled letters (WWeeaatthheerr -> Weather)
    def de_double(m):
        s = m.group(0)
        if len(s) >= 4 and all(s[i] == s[i+1] for i in range(0, len(s), 2)):
            return "".join([s[i] for i in range(0, len(s), 2)])
        return s
    text = re.sub(r'([A-Za-z])\1([A-Za-z])\2', de_double, text)
    return text

def clean_page_lines(page_text: str) -> str:
    """Removes standalone page numbers, recurrent running headers, and short noise."""
    lines = page_text.split('\n')
    cleaned = []
    for l in lines:
        s = l.strip()
        if not s: continue
        # Ignore standalone single numbers (common page numbers)
        if re.match(r'^\d{1,4}$', s): continue
        if len(s) < 3 and s.isdigit(): continue
        # Ignore common PDF watermarks/footer artifacts
        if re.match(r'^(page\s+\d+|http[s]?://|\bwww\.)', s, re.IGNORECASE): continue
        cleaned.append(s)
    return "\n".join(cleaned)

def detect_chapters_and_topics(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Intelligently identifies chapters and subtopics from page text.
    Fallback to logical sections if no explicit chapter titles are found.
    """
    chapters = []
    
    # Regex patterns for chapter titles
    chapter_regexes = [
        re.compile(r'(?i)^\s*(?:chapter|unit|module|part)\s+([0-9ivxlcdm]+)[:\.\-\s]+([^\n\r]+)', re.MULTILINE),
        re.compile(r'(?i)^\s*(?:chapter|unit|module|part)\s+([0-9ivxlcdm]+)\s*$', re.MULTILINE),
        re.compile(r'(?i)^\s*([0-9]{1,2})\.\s+([A-Z][A-Za-z0-9\s,\-\(\)\':]{3,70})\s*$', re.MULTILINE)
    ]
    
    current_chapter = None
    
    for p_idx, page in enumerate(pages):
        page_num = page["page_num"]
        p_text = page["text"]
        lines = p_text.split('\n')
        
        found_chapter_on_page = False
        
        for l_idx, line in enumerate(lines[:12]):  # Usually chapter heading is in top 12 lines
            line_str = line.strip()
            if not line_str: continue
            
            # Match chapter header
            match = None
            ch_num = ""
            ch_name = ""
            
            for rx in chapter_regexes:
                m = rx.search(line_str)
                if m:
                    match = m
                    ch_num = m.group(1).strip()
                    if m.lastindex and m.lastindex >= 2:
                        ch_name = m.group(2).strip()
                    elif l_idx + 1 < len(lines):
                        ch_name = lines[l_idx + 1].strip()
                    break
            
            if match and ch_name and len(ch_name) > 2:
                # Close previous chapter
                if current_chapter:
                    current_chapter["end_page"] = page_num - 1 if page_num > current_chapter["start_page"] else page_num
                    chapters.append(current_chapter)
                
                full_title = f"Chapter {ch_num}: {ch_name}".strip() if ch_num and not ch_name.lower().startswith("chapter") else ch_name
                current_chapter = {
                    "chapter_number": ch_num or str(len(chapters) + 1),
                    "chapter_title": full_title,
                    "start_page": page_num,
                    "end_page": page_num,
                    "topics": []
                }
                found_chapter_on_page = True
                break
        
        # Scan for topics (subsections)
        if current_chapter:
            current_chapter["end_page"] = page_num
            for line in lines:
                topic_match = re.search(r'^\s*([0-9]{1,2}\.[0-9]{1,2})\s+([A-Z][A-Za-z0-9\s\-:]{3,60})$', line.strip())
                if topic_match:
                    t_title = f"{topic_match.group(1)} {topic_match.group(2).strip()}"
                    if t_title not in current_chapter["topics"]:
                        current_chapter["topics"].append(t_title)

    if current_chapter:
        chapters.append(current_chapter)
        
    # --- Fallback: If no chapters detected or only 1 chapter across a large book ---
    total_pages = len(pages)
    if not chapters or (len(chapters) == 1 and total_pages > 40):
        print(f"[CHAPTER-DETECT] Few or no chapters detected. Generating sequential study modules...")
        chapters = []
        pages_per_module = 25 if total_pages > 50 else (15 if total_pages > 20 else max(1, total_pages))
        num_modules = max(1, (total_pages + pages_per_module - 1) // pages_per_module)
        
        for m_idx in range(num_modules):
            s_page = (m_idx * pages_per_module) + 1
            e_page = min(total_pages, (m_idx + 1) * pages_per_module)
            chapters.append({
                "chapter_number": str(m_idx + 1),
                "chapter_title": f"Module {m_idx + 1}: Content (Pages {s_page}-{e_page})",
                "start_page": s_page,
                "end_page": e_page,
                "topics": [f"Section {m_idx+1}.1: Key Concepts (P.{s_page}-{s_page+5})"]
            })
            
    return chapters

async def extract_text_via_vision(file_path: str, status_query: dict = None) -> List[Dict[str, Any]]:
    """Converts PDF pages to images and uses GPT-4o-mini Vision to extract text."""
    pages = []
    doc = pymupdf.open(file_path)
    total = len(doc)
    for i in range(total):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        img_data = pix.tobytes("png")
        base64_image = base64.b64encode(img_data).decode('utf-8')

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all educational and examination text from this textbook page. Preserve reading order, formulas, tables, headings, and diagram explanations."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=2500,
        )
        p_text = response.choices[0].message.content or ""
        pages.append({"page_num": i + 1, "text": clean_page_lines(normalize_text(p_text))})
        
        if status_query:
            pct = 10 + int(((i + 1) / total) * 25)
            await db.chapter_status.update_one(status_query, {"$set": {"progress": pct, "updated_at": datetime.now(timezone.utc)}})
            
    doc.close()
    return pages

# --------------------------
# 1. EXAM CATEGORIES API
# --------------------------
@router.get("/competitive-exams/categories")
async def get_categories():
    """Retrieve all competitive exam categories. Seeds default categories if collection is empty."""
    count = await db.competitive_exam_categories.count_documents({})
    if count == 0:
        now = datetime.now(timezone.utc)
        docs = [{**cat, "created_at": now, "updated_at": now} for cat in DEFAULT_CATEGORIES]
        await db.competitive_exam_categories.insert_many(docs)
    
    categories = await db.competitive_exam_categories.find({}).sort("category_name", 1).to_list(None)
    for c in categories:
        c["_id"] = str(c["_id"])
    return {"categories": categories}

# --------------------------
# 2. EXAM BLUEPRINTS API (READ-ONLY)
# --------------------------
@router.get("/competitive-exams/api/exams")
async def get_exams(category_id: Optional[str] = None):
    """Retrieve all competitive exam configurations. Seeds defaults if collection is empty."""
    count = await db.competitive_exams.count_documents({})
    if count == 0:
        now = datetime.now(timezone.utc)
        docs = [{**e, "created_at": now, "updated_at": now} for e in DEFAULT_EXAMS]
        await db.competitive_exams.insert_many(docs)

    query = {}
    if category_id:
        query["$or"] = [{"category_id": category_id}, {"category_name": category_id}]
        
    exams = await db.competitive_exams.find(query).sort("exam_name", 1).to_list(None)
    for e in exams:
        e["_id"] = str(e["_id"])
    return {"exams": exams}



# --------------------------
# 3. FULL TEXTBOOK UPLOAD & PIPELINE
# --------------------------
@router.post("/competitive-exams/textbook/upload-full")
async def upload_full_textbook(
    background_tasks: BackgroundTasks,
    exam_category: str = Form(...),
    exam_name: str = Form(...),
    exam_id: Optional[str] = Form(None),
    exam_year: Optional[str] = Form(None),
    syllabus_version: Optional[str] = Form(None),
    subject: str = Form(...),
    language: str = Form("en"),
    textbook_title: str = Form(...),
    publisher: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    syllabus_mapping: Optional[str] = Form(None),
    force_vision: Optional[str] = Form("false"),
    file: UploadFile = File(...),
    current_admin: dict = Depends(require_permission("Competitive Exams", "create"))
):
    """
    Ingests ONE complete competitive exam textbook PDF.
    Extracts text, identifies chapter and topic hierarchy, chunks, generates embeddings,
    persists to MongoDB, strictly verifies persistence, and automatically DELETES the uploaded PDF.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
        
    file_id = str(uuid.uuid4())
    temp_filename = f"comp_tb_{file_id}.pdf"
    file_path = os.path.join(UPLOAD_DIR, temp_filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    now = datetime.now(timezone.utc)
    textbook_doc = {
        "module_type": "competitive_exam",
        "exam_category": exam_category.strip(),
        "exam_name": exam_name.strip(),
        "exam_id": exam_id.strip() if exam_id else None,
        "exam_year": exam_year.strip() if exam_year else str(now.year),
        "syllabus_version": syllabus_version.strip() if syllabus_version else "Latest",
        "subject": subject.strip(),
        "language": language.strip(),
        "textbook_title": textbook_title.strip(),
        "board": "Competitive Exams",
        "standard": exam_name.strip(),
        "state": exam_category.strip(),
        "textbook_name": textbook_title.strip(),
        "publication_year": exam_year.strip() if exam_year else str(now.year),
        "publisher": publisher.strip() if publisher else None,
        "description": description.strip() if description else None,
        "syllabus_mapping": syllabus_mapping.strip() if syllabus_mapping else None,
        "original_filename": file.filename,
        "page_count": 0,
        "detected_chapter_count": 0,
        "stored_chunk_count": 0,
        "chapters": [],
        "chapter_metadata": [],
        "pdf_deleted": False,
        "pdf_deletion_status": "pending",
        "pdf_deletion_details": "Scheduled for auto-deletion after extraction and vectorization validation.",
        "status": "uploaded",
        "stage": "uploaded",
        "progress": 5,
        "error": None,
        "created_at": now,
        "updated_at": now
    }
    
    res = await db.textbook.insert_one(textbook_doc)
    textbook_id = str(res.inserted_id)
    
    # Initialize Status record for UI polling
    await db.chapter_status.update_one(
        {"textbook_id": textbook_id},
        {"$set": {
            "textbook_id": textbook_id,
            "textbook_title": textbook_title,
            "exam_name": exam_name,
            "subject": subject,
            "status": "processing",
            "stage": "uploaded",
            "progress": 5,
            "pdf_deleted": False,
            "pdf_deletion_status": "pending",
            "updated_at": now
        }},
        upsert=True
    )
    
    background_tasks.add_task(
        process_competitive_textbook_worker,
        textbook_id=textbook_id,
        file_path=file_path,
        original_filename=file.filename,
        force_vision=(force_vision.lower() == "true"),
        admin_sub=current_admin["sub"],
        admin_role=current_admin["role"]
    )
    
    return {
        "status": "processing",
        "textbook_id": textbook_id,
        "message": f"Full textbook '{textbook_title}' received. Asynchronous extraction, embedding, and automatic PDF deletion started."
    }

async def process_competitive_textbook_worker(
    textbook_id: str,
    file_path: str,
    original_filename: str,
    force_vision: bool,
    admin_sub: str,
    admin_role: str
):
    """
    Background worker:
    1. Extract full text (pdfplumber or Vision)
    2. Clean & normalize content
    3. Detect chapters & topic hierarchy
    4. Chunk with sliding window
    5. Generate text-embedding-3-large vectors
    6. Persist to MongoDB (db.textbook & db.textbook_chapters)
    7. Strictly Validate content in MongoDB
    8. MANDATORY: Delete PDF from upload storage and update audit status
    """
    status_query = {"textbook_id": textbook_id}
    print(f"[COMP-TB] Starting full textbook ingestion for: {textbook_id} ({original_filename})")
    
    try:
        # STEP 1: EXTRACTION (10% - 35%)
        await db.chapter_status.update_one(status_query, {"$set": {"stage": "extracting", "progress": 10, "updated_at": datetime.now(timezone.utc)}})
        await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"status": "extracting", "stage": "extracting", "progress": 10}})
        
        pages = []
        if force_vision:
            print(f"[COMP-TB] Force Vision Extraction active. Running PyMuPDF + GPT-4o-mini Vision...")
            pages = await extract_text_via_vision(file_path, status_query)
        else:
            print(f"[COMP-TB] Running standard extraction via pdfplumber...")
            with pdfplumber.open(file_path) as pdf:
                total_p = len(pdf.pages)
                for idx, page in enumerate(pdf.pages):
                    raw_text = page.extract_text() or ""
                    cleaned = clean_page_lines(normalize_text(raw_text))
                    pages.append({"page_num": idx + 1, "text": cleaned})
                    
                    if (idx + 1) % 5 == 0 or idx + 1 == total_p:
                        pct = 10 + int(((idx + 1) / total_p) * 25)
                        await db.chapter_status.update_one(status_query, {"$set": {"progress": pct, "total_pages": total_p, "updated_at": datetime.now(timezone.utc)}})

        total_pages = len(pages)
        if total_pages == 0:
            raise Exception("PDF is empty or contains no readable pages.")
            
        full_extracted_chars = sum(len(p["text"]) for p in pages)
        print(f"[COMP-TB] Extracted {total_pages} pages ({full_extracted_chars} total characters).")
        
        if full_extracted_chars < 50:
            raise Exception("No readable text found. If this is a scanned document, please enable the 'Force Vision Extraction' toggle.")

        # STEP 2 & 3: DETECT CHAPTERS & TOPICS (40% - 45%)
        await db.chapter_status.update_one(status_query, {"$set": {"stage": "detecting_chapters", "progress": 40, "updated_at": datetime.now(timezone.utc)}})
        await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"status": "detecting_chapters", "stage": "detecting_chapters", "progress": 40}})
        
        detected_chapters = detect_chapters_and_topics(pages)
        print(f"[COMP-TB] Detected {len(detected_chapters)} chapters/sections.")
        
        # Build chapter page text map
        page_dict = {p["page_num"]: p["text"] for p in pages}
        chapter_titles = [c["chapter_title"] for c in detected_chapters]

        # STEP 4: SLIDING WINDOW CHUNKING & EMBEDDINGS (45% - 80%)
        await db.chapter_status.update_one(status_query, {"$set": {"stage": "generating_embeddings", "progress": 45, "detected_chapters": len(detected_chapters), "updated_at": datetime.now(timezone.utc)}})
        await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"status": "generating_embeddings", "stage": "generating_embeddings", "progress": 45}})
        
        tb_doc = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
        
        PASSAGE_SIZE = 4000
        PASSAGE_OVERLAP = 400
        raw_chunks = []
        
        for ch in detected_chapters:
            s_page = ch["start_page"]
            e_page = ch["end_page"]
            ch_text = "\n\n".join(page_dict.get(pn, "") for pn in range(s_page, e_page + 1) if page_dict.get(pn, "").strip())
            
            if not ch_text.strip():
                continue
                
            if len(ch_text) <= PASSAGE_SIZE:
                raw_chunks.append({
                    "chapter": ch,
                    "page_range": f"{s_page}-{e_page}",
                    "content": ch_text.strip()
                })
            else:
                for start_i in range(0, len(ch_text), PASSAGE_SIZE - PASSAGE_OVERLAP):
                    chunk_text = ch_text[start_i:start_i + PASSAGE_SIZE].strip()
                    if chunk_text:
                        raw_chunks.append({
                            "chapter": ch,
                            "page_range": f"{s_page}-{e_page}",
                            "content": chunk_text
                        })

        print(f"[COMP-TB] Generated {len(raw_chunks)} chunks. Generating OpenAI embeddings...")
        
        valid_docs = []
        total_chunks = len(raw_chunks)
        
        for c_idx, chunk in enumerate(raw_chunks):
            emb = await client.embeddings.create(model="text-embedding-3-large", input=chunk["content"])
            vector = emb.data[0].embedding
            
            # Log usage
            if hasattr(emb, 'usage') and emb.usage:
                from app.utils.ai_usage_logger import log_ai_usage
                await log_ai_usage("ADMIN", "Competitive Exam Textbook Embedding", "text-embedding-3-large", emb.usage)

            valid_docs.append({
                "textbook_id": textbook_id,
                "module_type": "competitive_exam",
                "exam_category": tb_doc.get("exam_category"),
                "exam_name": tb_doc.get("exam_name"),
                "exam_id": tb_doc.get("exam_id"),
                "exam_year": tb_doc.get("exam_year"),
                "syllabus_version": tb_doc.get("syllabus_version"),
                "subject": tb_doc.get("subject"),
                "language": tb_doc.get("language"),
                "chapter_title": chunk["chapter"]["chapter_title"],
                "chapter_number": chunk["chapter"]["chapter_number"],
                "topics": chunk["chapter"].get("topics", []),
                "page_range": chunk["page_range"],
                "content": chunk["content"],
                "passage_index": c_idx,
                "vector": vector,
                "detected_language": tb_doc.get("language", "en"),
                "created_at": datetime.now(timezone.utc)
            })
            
            pct = 45 + int(((c_idx + 1) / total_chunks) * 35)
            await db.chapter_status.update_one(status_query, {"$set": {"progress": pct, "processed_chunks": c_idx + 1, "updated_at": datetime.now(timezone.utc)}})

        # STEP 5: SAVE TO MONGODB (80% - 85%)
        if not valid_docs:
            raise Exception("No valid passage chunks could be formed from the extracted textbook content.")

        await db.chapter_status.update_one(status_query, {"$set": {"stage": "saving", "progress": 80, "updated_at": datetime.now(timezone.utc)}})
        await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"status": "saving", "stage": "saving", "progress": 80}})
        
        # Atomic clean old chunks & insert new
        await db.textbook_chapters.delete_many({"textbook_id": textbook_id})
        await db.textbook_chapters.insert_many(valid_docs)
        
        await db.textbook.update_one(
            {"_id": ObjectId(textbook_id)},
            {"$set": {
                "page_count": total_pages,
                "detected_chapter_count": len(detected_chapters),
                "stored_chunk_count": len(valid_docs),
                "chapters": chapter_titles,
                "chapter_metadata": detected_chapters,
                "updated_at": datetime.now(timezone.utc)
            }}
        )

        # STEP 6: STRICT VALIDATION (85% - 90%)
        await db.chapter_status.update_one(status_query, {"$set": {"stage": "validating", "progress": 85, "updated_at": datetime.now(timezone.utc)}})
        await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"status": "validating", "stage": "validating", "progress": 85}})
        
        stored_count = await db.textbook_chapters.count_documents({"textbook_id": textbook_id})
        if stored_count == 0 or stored_count != len(valid_docs):
            raise Exception(f"Database persistence validation failed! Expected {len(valid_docs)} passages, found {stored_count}.")
            
        sample_doc = await db.textbook_chapters.find_one({"textbook_id": textbook_id})
        if not sample_doc or not sample_doc.get("vector") or len(sample_doc["vector"]) != 3072:
            raise Exception("Vector embedding validation failed! Stored vectors are missing or invalid.")
            
        print(f"[COMP-TB] MongoDB validation SUCCESS: Verified {stored_count} stored passages with 3072-dim embeddings.")

        # STEP 7: MANDATORY UPLOADED PDF DELETION (90% - 100%)
        await db.chapter_status.update_one(status_query, {"$set": {"stage": "deleting_pdf", "progress": 92, "updated_at": datetime.now(timezone.utc)}})
        await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"status": "deleting_pdf", "stage": "deleting_pdf", "progress": 92}})
        
        pdf_deleted_successfully = False
        cleanup_error_msg = ""
        
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                # Verify deletion
                if not os.path.exists(file_path):
                    pdf_deleted_successfully = True
                    print(f"[COMP-TB] PDF DELETION SUCCESS: Deleted {file_path}")
                else:
                    cleanup_error_msg = "File still exists on disk after delete call."
            except Exception as e:
                # Retry once after brief pause (handles brief Windows lock)
                await asyncio.sleep(1)
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    pdf_deleted_successfully = not os.path.exists(file_path)
                except Exception as e2:
                    cleanup_error_msg = str(e2)
                    print(f"[COMP-TB] PDF DELETION FAILED: {e2}")
        else:
            pdf_deleted_successfully = True
            
        final_now = datetime.now(timezone.utc)
        if pdf_deleted_successfully:
            await db.textbook.update_one(
                {"_id": ObjectId(textbook_id)},
                {"$set": {
                    "pdf_deleted": True,
                    "pdf_deletion_status": "deleted",
                    "pdf_deletion_timestamp": final_now,
                    "pdf_deletion_details": "Source PDF successfully verified and deleted from server storage.",
                    "status": "completed",
                    "stage": "completed",
                    "progress": 100,
                    "updated_at": final_now
                }}
            )
            await db.chapter_status.update_one(
                status_query,
                {"$set": {
                    "status": "completed",
                    "stage": "completed",
                    "progress": 100,
                    "pdf_deleted": True,
                    "pdf_deletion_status": "deleted",
                    "updated_at": final_now
                }}
            )
            print(f"[COMP-TB] INGESTION COMPLETED: Textbook {textbook_id} is 100% processed and PDF deleted.")
        else:
            # Stored content is safe, but cleanup needs attention
            await db.textbook.update_one(
                {"_id": ObjectId(textbook_id)},
                {"$set": {
                    "pdf_deleted": False,
                    "pdf_deletion_status": "failed",
                    "pdf_deletion_details": f"Content safely stored, but automatic deletion failed: {cleanup_error_msg}",
                    "status": "cleanup_failed",
                    "stage": "cleanup_failed",
                    "progress": 98,
                    "updated_at": final_now
                }}
            )
            await db.chapter_status.update_one(
                status_query,
                {"$set": {
                    "status": "cleanup_failed",
                    "stage": "cleanup_failed",
                    "progress": 98,
                    "pdf_deleted": False,
                    "pdf_deletion_status": "failed",
                    "error": f"Content safely saved, but PDF cleanup failed: {cleanup_error_msg}",
                    "updated_at": final_now
                }}
            )

        await log_admin_activity(
            admin_sub,
            admin_role,
            "upload_competitive_textbook",
            f"Successfully processed competitive textbook '{tb_doc.get('textbook_title')}' ({stored_count} passages, PDF deleted: {pdf_deleted_successfully})",
            status="completed" if pdf_deleted_successfully else "cleanup_failed"
        )

    except Exception as exc:
        err_str = str(exc)
        print(f"[COMP-TB] CRITICAL WORKER ERROR for {textbook_id}: {err_str}")
        now_err = datetime.now(timezone.utc)
        await db.chapter_status.update_one(
            status_query,
            {"$set": {"status": "failed", "stage": "failed", "error": err_str, "updated_at": now_err}}
        )
        await db.textbook.update_one(
            {"_id": ObjectId(textbook_id)},
            {"$set": {"status": "failed", "stage": "failed", "error": err_str, "updated_at": now_err}}
        )
        await log_admin_activity(
            admin_sub,
            admin_role,
            "upload_competitive_textbook",
            f"Failed to process competitive textbook {textbook_id}: {err_str}",
            status="failed"
        )

# --------------------------
# 4. TEXTBOOK STATUS & RETRY API
# --------------------------
@router.get("/competitive-exams/textbook-status/{textbook_id}")
async def get_textbook_status(textbook_id: str):
    """Real-time polling endpoint for frontend tracking of ingestion stages."""
    status_doc = await db.chapter_status.find_one({"textbook_id": textbook_id})
    tb_doc = await db.textbook.find_one({"_id": ObjectId(textbook_id)}) if ObjectId.is_valid(textbook_id) else None
    
    if not status_doc and not tb_doc:
        return {"status": "not_found", "progress": 0}
        
    return {
        "textbook_id": textbook_id,
        "status": status_doc.get("status") if status_doc else tb_doc.get("status"),
        "stage": status_doc.get("stage") if status_doc else tb_doc.get("stage"),
        "progress": status_doc.get("progress", 0) if status_doc else tb_doc.get("progress", 0),
        "total_pages": status_doc.get("total_pages") or (tb_doc.get("page_count") if tb_doc else 0),
        "detected_chapters": status_doc.get("detected_chapters") or (tb_doc.get("detected_chapter_count") if tb_doc else 0),
        "processed_chunks": status_doc.get("processed_chunks") or (tb_doc.get("stored_chunk_count") if tb_doc else 0),
        "pdf_deleted": status_doc.get("pdf_deleted") if status_doc else tb_doc.get("pdf_deleted", False),
        "pdf_deletion_status": status_doc.get("pdf_deletion_status") if status_doc else tb_doc.get("pdf_deletion_status", "pending"),
        "error": status_doc.get("error") if status_doc else tb_doc.get("error")
    }

# --------------------------
# 4. INGESTED TEXTBOOKS API
# --------------------------
@router.get("/competitive-exams/textbooks")
async def list_competitive_textbooks(
    category: Optional[str] = None,
    exam_name: Optional[str] = None,
    subject: Optional[str] = None
):
    """Retrieve all uploaded competitive exam textbooks."""
    query = {
        "$or": [
            {"module_type": "competitive_exam"},
            {"exam_name": {"$exists": True, "$ne": None, "$ne": ""}},
            {"exam_category": {"$exists": True, "$ne": None, "$ne": ""}}
        ]
    }
    and_clauses = []
    if category:
        and_clauses.append({"$or": [{"exam_category": category}, {"board": category}, {"state": category}]})
    if exam_name:
        and_clauses.append({"$or": [{"exam_name": exam_name}, {"standard": exam_name}]})
    if subject:
        and_clauses.append({"subject": subject})
    if and_clauses:
        query = {"$and": [query] + and_clauses}
    
    textbooks = await db.textbook.find(query).sort("created_at", -1).to_list(None)
    for t in textbooks:
        t["_id"] = str(t["_id"])
        t["module_type"] = "competitive_exam"
        t["textbook_title"] = t.get("textbook_title") or t.get("textbook_name") or f"{t.get('subject', 'General')} Textbook"
        t["exam_name"] = t.get("exam_name") or t.get("standard") or "General"
        t["exam_category"] = t.get("exam_category") or t.get("board") or "Competitive Exams"
        t["exam_year"] = t.get("exam_year") or t.get("publication_year") or ""
        t["stored_chunk_count"] = t.get("stored_chunk_count", 0)
    return {"textbooks": textbooks}



# --------------------------
# 5. RAG QUESTION GENERATION
# --------------------------
@router.post("/competitive-exams/generate-questions")
async def trigger_generate_questions(
    payload: dict = Body(...),
    current_admin: dict = Depends(require_permission("Competitive Exams", "create"))
):
    """
    Triggers RAG-based question paper generation for competitive exams.
    Retrieves stored passages from db.textbook_chapters (without needing original PDF),
    ranks passages via dynamic semantic search, and generates exam-aligned papers with answer keys.
    """
    exam_id = payload.get("exam_id")
    exam_name_input = (payload.get("exam_name") or "").strip()
    textbook_id = payload.get("textbook_id")
    subject = payload.get("subject", "General Studies")
    chapters = payload.get("chapters", [])
    papers_count = int(payload.get("paper_count", 1))
    total_marks = int(payload.get("total_marks", 100))
    duration_minutes = int(payload.get("duration_minutes", 120))
    total_questions = int(payload.get("total_questions", 50))
    negative_marking = payload.get("negative_marking", True)
    negative_penalty = float(payload.get("negative_marking_penalty", 0.33))
    language = payload.get("language", "en")
    
    if not textbook_id:
        raise HTTPException(status_code=400, detail="Textbook selection is required.")
        
    tb = await db.textbook.find_one({"_id": ObjectId(textbook_id)}) if ObjectId.is_valid(textbook_id) else None
    if not tb:
        raise HTTPException(status_code=404, detail="Selected textbook not found in database.")
        
    exam = await db.competitive_exams.find_one({"_id": ObjectId(exam_id)}) if exam_id and ObjectId.is_valid(exam_id) else {}

    resolved_exam_name = exam.get("exam_name") if exam else (exam_name_input or tb.get("exam_name", "Competitive Exam"))
    resolved_category = exam.get("category_name") if exam else (tb.get("exam_category") or tb.get("board", "Competitive Exams"))

    task_doc = {
        "module_type": "competitive_exam",
        "exam_id": exam_id,
        "exam_name": resolved_exam_name,
        "exam_category": resolved_category,
        "textbook_id": textbook_id,
        "textbook_title": tb.get("textbook_title", "Textbook"),
        "subject": subject,
        "chapters": chapters if chapters else tb.get("chapters", []),
        "papers_count": papers_count,
        "total_marks": total_marks,
        "duration_minutes": duration_minutes,
        "total_questions": total_questions,
        "negative_marking": negative_marking,
        "negative_penalty": negative_penalty,
        "language": language,
        "status": "queued",
        "progress": 0,
        "created_at": datetime.now(timezone.utc)
    }
    
    res = await db.question_tasks.insert_one(task_doc)
    task_id = str(res.inserted_id)
    
    asyncio.create_task(
        generate_competitive_questions_worker(task_id, current_admin["sub"], current_admin["role"])
    )
    
    return {"status": "started", "task_id": task_id, "message": "Question paper generation started."}

async def generate_competitive_questions_worker(task_id: str, admin_sub: str, admin_role: str):
    task = await db.question_tasks.find_one({"_id": ObjectId(task_id)})
    if not task: return
    
    await db.question_tasks.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": "running", "progress": 10}})
    
    try:
        textbook_id = task["textbook_id"]
        chapters = task.get("chapters", [])
        total_questions = task.get("total_questions", 50)
        total_marks = task.get("total_marks", 100)
        papers_count = task.get("papers_count", 1)
        exam_name = task.get("exam_name", "Competitive Exam")
        subject = task.get("subject", "General Studies")
        negative_penalty = task.get("negative_penalty", 0.33)
        language = task.get("language", "en")
        
        # 1. RETRIEVE RELEVANT PASSAGES FROM MONGODB (RAG)
        rag_query = {"textbook_id": textbook_id}
        if chapters:
            rag_query["chapter_title"] = {"$in": chapters}
            
        passages = await db.textbook_chapters.find(rag_query).to_list(None)
        if not passages:
            # Fallback to any passages for this textbook
            passages = await db.textbook_chapters.find({"textbook_id": textbook_id}).to_list(None)
            
        if not passages:
            raise Exception("No extracted passages found for this textbook in MongoDB.")
            
        print(f"[RAG-COMP] Loaded {len(passages)} passages for question generation.")
        
        # Group passages by chapter
        chapter_map = {}
        for p in passages:
            ct = p.get("chapter_title", "General")
            if ct not in chapter_map: chapter_map[ct] = []
            chapter_map[ct].append(p)
            
        generated_paper_ids = []
        used_questions_all = []

        for p_idx in range(papers_count):
            print(f"[RAG-COMP] Generating Paper {p_idx+1}/{papers_count} for {exam_name}...")
            
            # 2. DYNAMIC SEMANTIC SEARCH FOR TOP PASSAGES
            selected_passages = []
            for ch_title, ch_passages in chapter_map.items():
                if len(ch_passages) <= 6:
                    selected_passages.extend(ch_passages)
                else:
                    # Semantic search based on paper index
                    if p_idx == 0:
                        query_text = f"Key concepts, foundational principles, definitions, and official facts in {ch_title}"
                    elif p_idx == 1:
                        query_text = f"Complex applications, analytical problems, historical contexts, and statutory provisions in {ch_title}"
                    else:
                        query_text = f"In-depth analysis, critical nuances, comparative evaluations, and exceptions in {ch_title}"
                        
                    emb_res = await client.embeddings.create(model="text-embedding-3-large", input=query_text)
                    q_vec = emb_res.data[0].embedding
                    
                    scored = []
                    for pass_item in ch_passages:
                        score = cosine_similarity(q_vec, pass_item.get("vector", []))
                        scored.append((score, pass_item))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    selected_passages.extend([item for _, item in scored[:6]])
                    
            context_blocks = []
            for sp in selected_passages[:30]:  # Cap context to prevent token explosion
                context_blocks.append(f"--- Chapter: {sp.get('chapter_title')} (P. {sp.get('page_range')}) ---\n{sp.get('content')}")
            
            context_text = "\n\n".join(context_blocks)
            
            # 3. CONSTRUCT COMPETITIVE EXAM PROMPT
            q_per_paper = total_questions
            marks_per_q = round(total_marks / q_per_paper, 2) if q_per_paper > 0 else 1
            neg_rule = f"{negative_penalty} marks deducted per incorrect answer" if task.get("negative_marking") else "No negative marks"
            
            exclusion_text = ""
            if used_questions_all:
                exclusion_text = "### PREVIOUSLY GENERATED QUESTIONS (DO NOT DUPLICATE):\n" + "\n".join(f"- {q}" for q in used_questions_all[:50]) + "\n"

            prompt = f"""You are an elite competitive examination paper setter for {exam_name}.
Your mission is to construct a rigorous, syllabus-aligned objective question paper based EXCLUSIVELY on the provided textbook excerpts.

### EXAM SPECIFICATIONS
- Examination: {exam_name}
- Subject: {subject}
- Total Questions: {q_per_paper}
- Total Marks: {total_marks}
- Marks Per Question: {marks_per_q}
- Negative Marking Rule: {neg_rule}
- Language: {language}

### RETRIEVED TEXTBOOK PASSAGES (AUTHORITATIVE SOURCE)
{context_text}

{exclusion_text}

### DIRECTIVES FOR COMPETITIVE EXAMS
1. Strict Grounding: Every question, option, and answer MUST be factually supported by the textbook excerpts. Do not invent facts or test unmentioned topics.
2. Formats: Generate standard objective MCQs with 4 options (A, B, C, D). You may include:
   - Direct conceptual MCQs
   - Statement-based MCQs (e.g. 'Consider the following statements... Which is/are correct?')
   - Assertion & Reason
   - Match the following
3. Options: Exactly ONE unambiguously correct option. All distractors must be plausible and academically valid.
4. Explanations: Provide a comprehensive explanation citing the chapter and concept for each question.
5. Difficulty: Distribute difficulty evenly (Easy: 30%, Medium: 50%, Hard: 20%).

### OUTPUT JSON FORMAT
Return ONLY valid JSON matching this schema:
{{
  "paper_title": "{exam_name} - Practice Paper {p_idx+1}",
  "exam_name": "{exam_name}",
  "subject": "{subject}",
  "total_marks": {total_marks},
  "time_limit": "{task.get('duration_minutes', 120)} MINUTES",
  "negative_marking_rule": "{neg_rule}",
  "sections": [
    {{
      "section_title": "Section A: Core Concepts & Practice",
      "questions": [
        {{
          "question_number": 1,
          "question": "Question text here?",
          "type": "MCQ",
          "options": {{
            "A": "Option A text",
            "B": "Option B text",
            "C": "Option C text",
            "D": "Option D text"
          }},
          "correct_answer": "A",
          "marks": {marks_per_q},
          "negative_marks": {negative_penalty},
          "difficulty": "Medium",
          "explanation": "Detailed explanation grounded in the textbook...",
          "chapter_reference": "Chapter reference name"
        }}
      ]
    }}
  ],
  "answer_key": {{
    "1": "A"
  }}
}}"""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.25,
                response_format={"type": "json_object"}
            )
            
            raw_json_str = response.choices[0].message.content or "{}"
            try:
                paper_data = json.loads(raw_json_str)
            except Exception:
                paper_data = {"paper_title": f"{exam_name} Paper {p_idx+1}", "sections": []}
                
            # Populate answer key if missing
            if not paper_data.get("answer_key"):
                ans_map = {}
                for sec in paper_data.get("sections", []):
                    for q in sec.get("questions", []):
                        q_num = str(q.get("question_number", ""))
                        if q_num and q.get("correct_answer"):
                            ans_map[q_num] = q.get("correct_answer")
                paper_data["answer_key"] = ans_map

            # Track question texts to prevent duplicates
            for sec in paper_data.get("sections", []):
                for q in sec.get("questions", []):
                    if q.get("question"):
                        used_questions_all.append(q["question"].strip())

            # 4. RENDER PDF VIA COMPETITIVE EXAM PDF LAYOUT SERVICE
            paper_id_val = f"comp_{task_id}_{p_idx+1}"
            pdf_filename = f"{GENERATED_PDF_DIR}/{paper_id_val}.pdf"
            
            try:
                save_competitive_exam_paper(paper_data, pdf_filename)
            except Exception as e:
                print(f"[RAG-COMP] PDF generation warning: {e}")

            # Save in db.generated_papers
            ins_res = await db.generated_papers.insert_one({
                "module_type": "competitive_exam",
                "task_id": task_id,
                "exam_id": task.get("exam_id"),
                "exam_name": exam_name,
                "textbook_id": textbook_id,
                "paper_index": p_idx + 1,
                "paper": paper_data,
                "pdf_path": pdf_filename,
                "created_at": datetime.now(timezone.utc)
            })
            generated_paper_ids.append(str(ins_res.inserted_id))
            
            pct = int(((p_idx + 1) / papers_count) * 90)
            await db.question_tasks.update_one({"_id": ObjectId(task_id)}, {"$set": {"progress": pct}})

        # Finish task
        await db.question_tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {
                "status": "completed",
                "progress": 100,
                "generated_paper_ids": generated_paper_ids,
                "completed_at": datetime.now(timezone.utc)
            }}
        )
        print(f"[RAG-COMP] Generated {len(generated_paper_ids)} competitive exam papers for task {task_id}.")
        
    except Exception as exc:
        err_msg = str(exc)
        print(f"[RAG-COMP] Task {task_id} failed: {err_msg}")
        await db.question_tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"status": "failed", "error": err_msg, "progress": 0}}
        )

@router.get("/competitive-exams/task-status/{task_id}")
async def get_task_status(task_id: str):
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task ID")
    task = await db.question_tasks.find_one({"_id": oid})
    if not task:
        return {"status": "not_found"}
    return {
        "status": task.get("status"),
        "progress": task.get("progress", 0),
        "error": task.get("error"),
        "generated_paper_ids": task.get("generated_paper_ids", [])
    }

# --------------------------
# 6. GENERATED PAPERS API
# --------------------------

@router.get("/competitive-exams/generated-paper/{paper_id}")
async def get_generated_paper(paper_id: str):
    try:
        oid = ObjectId(paper_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid paper ID")
    paper = await db.generated_papers.find_one({"_id": oid})
    if not paper:
        raise HTTPException(status_code=404, detail="Generated paper not found")
    paper["_id"] = str(paper["_id"])
    filename = os.path.basename(paper.get("pdf_path") or "")
    paper["pdf_url"] = f"/generated_papers/{filename}" if filename else ""
    return {"paper": paper}

@router.delete("/competitive-exams/generated-paper/{paper_id}")
async def delete_generated_paper(paper_id: str, current_admin: dict = Depends(require_permission("Competitive Exams", "delete"))):
    try:
        oid = ObjectId(paper_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid paper ID")
    paper = await db.generated_papers.find_one({"_id": oid})
    if not paper:
        raise HTTPException(status_code=404, detail="Generated paper not found")
        
    pdf_p = paper.get("pdf_path")
    if pdf_p and os.path.exists(pdf_p):
        try: os.remove(pdf_p)
        except Exception: pass
        
    await db.generated_papers.delete_one({"_id": oid})
    return {"status": "success", "message": "Question paper deleted successfully."}


