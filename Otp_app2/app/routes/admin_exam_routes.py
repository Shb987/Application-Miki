# exam_module.py

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
from datetime import datetime, timezone
from app.utils.admin_auth import get_current_admin
from fastapi import Depends
from app.core.database import db
from openai import AsyncOpenAI

# --------------------------
# CONFIGURATION / CONSTANTS
# --------------------------

# OpenAI Client (Async — non-blocking event loop)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
print("OpenAI AsyncClient Initialized Successfully!")

router = APIRouter(tags=["Exam Module"])

UPLOAD_DIR = "app/static/textbook"
os.makedirs(UPLOAD_DIR, exist_ok=True)

GENERATED_PDF_DIR = "app/static/generated_papers"
os.makedirs(GENERATED_PDF_DIR, exist_ok=True)


templates = Jinja2Templates(directory="../new/admin/template")

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

# --------------------------
# UTILITIES
# --------------------------

def _safe(obj, key, default=""):
    return obj.get(key, default) if isinstance(obj, dict) else default

def get_exam_structure(standard: int, total: int):
    if standard <= 8:
        return EXAM_STRUCTURES.get(standard)
    if standard in [9, 10]:
        return HIGH_SCHOOL.get(total)
    return PLUS_TWO.get(total)

def validate_fix_marks(paper: dict, required_total: int):
    total = sum(q.get("marks", 0) for q in paper["questions"])
    diff = required_total - total
    if diff != 0 and paper["questions"]:
        paper["questions"][-1]["marks"] += diff
    return paper

# # --------------------------
# # ROUTES - PAGE TEMPLATES
# # --------------------------

# @router.get("/exam_module-page")
# async def exam_module_page(request: Request):
#     return templates.TemplateResponse("Exammodule.html", {"request": request})

# @router.get("/question_generation-page")
# async def question_generation_page(request: Request):
#     return templates.TemplateResponse("question_generation.html", {"request": request})

# @router.get("/generated-question_view-page")
# async def generated_question_page(request: Request):
#     return templates.TemplateResponse("view_questions.html", {"request": request})

# --------------------------
# ROUTES - SYLLABUS
# --------------------------


@router.post("/upload-textbook", dependencies=[Depends(get_current_admin)])
async def upload_textbook(
    textbook_board: str = Form(...),
    standard: str = Form(...),
    state: str = Form(...),
    subject: str = Form(...),
    count: int = Form(...),
    textbook_pdf: UploadFile = File(...)
):
    if textbook_pdf.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF allowed")

    file_id = str(uuid.uuid4())
    filename = f"{file_id}.pdf"
    file_path = os.path.join(UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(await textbook_pdf.read())

    text_content = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text_content += (page.extract_text() or "") + "\n"
    except:
        text_content = ""

    data = {
        "board": textbook_board,
        "standard": standard,
        "state": state,
        "subject": subject,
        "question_count": count,
        "file_path": file_path,
        "text_content": text_content,
        "processed": False,
        "status": "queued",
        "progress": 0,
        "created_at": datetime.now(timezone.utc)
    }

    result = await db.textbook.insert_one(data)
    return {"status": "uploaded", "textbook_id": str(result.inserted_id)}

@router.post("/process-textbook/{textbook_id}", dependencies=[Depends(get_current_admin)])
async def process_textbook_trigger(textbook_id: str):
    textbook = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
    if not textbook:
        raise HTTPException(status_code=404, detail="Textbook not found")

    asyncio.create_task(process_textbook_worker(textbook_id))
    return {"status": "started", "message": "Processing started in background", "textbook_id": textbook_id}

@router.get("/textbook/status/{textbook_id}", dependencies=[Depends(get_current_admin)])
async def textbook_status(textbook_id: str):
    data = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
    if not data:
        raise HTTPException(status_code=404, detail="Invalid ID")
    data["_id"] = str(data["_id"])
    return data

# --------------------------
# BACKGROUND WORKERS
# --------------------------

async def process_textbook_worker(textbook_id: str):
    await db.textbook.update_one(
        {"_id": ObjectId(textbook_id)},
        {"$set": {"status": "extracting", "progress": 10}}
    )

    textbook = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
    text = textbook.get("text_content", "")

    prompt = f"""
You are an expert textbook analyzer for Kerala SCERT textbooks.
Your task is to extract accurate chapter titles and content from the provided textbook text.

IMPORTANT:
- IGNORE front matter and back matter such as:
  - "The National Anthem"
  - "Pledge"
  - "Constitution of India"
  - "Preface", "Foreword", "Teachers' Note"
  - "Dear Students", "Instructions"
- Extract ONLY the actual educational chapters (e.g., "Chapter 1: ...", "Unit 1: ...", "1. ...").
- If a chapter has a number and a title, combine them (e.g., "Chapter 1: The Dawn of History").

Return STRICT VALID JSON ONLY in this format:
[
  {{
    "chapter": "Exact Chapter Name",
    "content": "Full combined content of the chapter"
  }}
]

Text to analyze:
{text}
"""

    try:
        ai = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        # Log usage
        if hasattr(ai, 'usage') and ai.usage:
            from app.utils.ai_usage_logger import log_ai_usage
            await log_ai_usage("ADMIN", "Textbook Extraction", "gpt-4o-mini", ai.usage)

        raw = ai.choices[0].message.content
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        chapters = json.loads(cleaned)
        chapter_titles = [c["chapter"].strip() for c in chapters]
        await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"chapters": chapter_titles}})
    except Exception:
        await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"status": "failed", "progress": 0}})
        return

    await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"status": "embedding", "progress": 40}})

    for idx, ch in enumerate(chapters):
        try:
            emb = await client.embeddings.create(model="text-embedding-3-large", input=ch["content"])
            vector = emb.data[0].embedding
            
            # Log usage
            if hasattr(emb, 'usage') and emb.usage:
                from app.utils.ai_usage_logger import log_ai_usage
                await log_ai_usage("ADMIN", "Textbook Embedding", "text-embedding-3-large", emb.usage)
            chapter_doc = {
                "textbook_id": textbook_id,
                "board": textbook["board"],
                "standard": textbook["standard"],
                "state": textbook["state"],
                "subject": textbook["subject"],
                "chapter_title": ch["chapter"].strip(),
                "content": ch["content"].strip(),
                "vector": vector,
                "created_at": datetime.utcnow(),
            }
            await db.textbook_chapters.insert_one(chapter_doc)
            progress = 40 + int((idx + 1) / len(chapters) * 55)
            await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"progress": progress}})
        except:
            pass

    await db.textbook.update_one({"_id": ObjectId(textbook_id)}, {"$set": {"status": "completed", "processed": True, "progress": 100}})

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
    return {"chapters": chapter_set}

# --------------------------
# ROUTES - QUESTION GENERATION
# --------------------------

@router.post("/generate-questions", dependencies=[Depends(get_current_admin)])
async def generate_questions_trigger(payload: dict = Body(...)):
    standard = payload.get("standard")
    subject = payload.get("subject")
    chapters = payload.get("chapters", [])
    papers = int(payload.get("papers", 1))
    marks = int(payload.get("marks", 50))

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
    # We query by standard (as string) because upload saves it as string
    chapter_docs = await db.textbook_chapters.find({
        "standard": str(std),
        "subject": subject,
        "chapter_title": {"$in": chapters}
    }).to_list(None)

    context_text = ""
    for doc in chapter_docs:
        # Limit content to avoid token overflow (approx 3000 words per chapter)
        # UPDATED: Increased to 100,000 chars to cover full chapters
        content_snippet = doc.get("content", "")[:100000]
        context_text += f"\n=== CHAPTER: {doc.get('chapter_title')} ===\n{content_snippet}\n"

    if not context_text:
        context_text = "No specific textbook content found. Generate based on general knowledge of these chapters."

    for p in range(papers):
        section_text = "\n".join([f"Section {key}: {val[0]} mark questions × {val[1]}" for key, val in sections.items()])

        prompt = f"""
Kerala SCERT Board Exam Question Paper Generator

Standard: {std}
Subject: {subject}
Chapters: {', '.join(chapters)}

Allowed Question Types: {allowed_types}

### TEXTBOOK CONTENT (SOURCE MATERIAL) ###
Use the following content to generate relevant questions. Do NOT ask questions outside this scope if possible.
{context_text}
### END CONTENT ###

### QUESTION STRUCTURE REQUIREMENTS ###
1. Generate questions STRICTLY grouped by sections.
2. Follow EXACT question counts specified below.
3. **CRITICAL**: Ensure questions are distributed EVENLY across all provided chapters/topics. Do not focus only on the first few pages. Cover the entire provided content.

{section_text}

### OUTPUT FORMAT ###
Respond with valid JSON only. No text outside JSON.

{{
  "paper_id": "{task_id}-{p+1}",
  "standard": "{std}",
  "subject": "{subject}",
  "chapters_used": {json.dumps(chapters)},
  "sections": [
    {{"section": "A", "marks_per_question": {list(sections.values())[0][0]}, "questions": []}},
    {{"section": "B", "marks_per_question": {list(sections.values())[1][0]}, "questions": []}},
    {{"section": "C", "marks_per_question": {list(sections.values())[2][0]}, "questions": []}}
  ]
}}
"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
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
        try:
            paper_filename = f"{GENERATED_PDF_DIR}/{paper_json['paper_id']}.pdf"
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

    # Mark job completed
    await db.question_tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": "completed", "generated": generated_ids}}
    )

# --------------------------
# ROUTES - JOB STATUS / GENERATED PAPERS
# --------------------------

@router.get("/question-task-status/{task_id}", dependencies=[Depends(get_current_admin)])
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
    return docs


@router.delete("/generated-paper/{paper_id}", dependencies=[Depends(get_current_admin)])
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


@router.get("/generated-papers/filter", dependencies=[Depends(get_current_admin)])
async def get_generated_papers_filtered(standard: str, subject: str):
    docs = await db.generated_papers.find({"paper.standard": standard, "paper.subject": subject}).to_list(None)

    for d in docs:
        d["_id"] = str(d["_id"])
        if "pdf_path" in d:
            # Match the mount point in main.py: app.mount("/generated_papers", ...)
            filename = os.path.basename(d["pdf_path"])
            d["pdf_url"] = f"/generated_papers/{filename}"

    return docs

