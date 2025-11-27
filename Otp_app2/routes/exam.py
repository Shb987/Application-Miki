from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi import BackgroundTasks
from datetime import datetime
from bson import ObjectId
import pdfplumber
import uuid
import json
import os
import asyncio

from core.database import db
from openai import OpenAI

# OpenAI Client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
print("OpenAI Client Initialized Successfully!")

router = APIRouter(tags=["Exam Module"])

UPLOAD_DIR = "Exams/syllabus"
os.makedirs(UPLOAD_DIR, exist_ok=True)

from fastapi import Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="../new/admin/template")

@router.get("/exam_module-page")
async def exam_module_page(request: Request):
    return templates.TemplateResponse("Exammodule.html", {"request": request})
@router.get("/question_generation-page")
async def question_generation_page(request: Request):
    return templates.TemplateResponse("question_generation.html", {"request": request})

# =====================================================================
# 1️⃣ Upload Syllabus  → FAST (No waiting)
# =====================================================================
@router.post("/upload-syllabus")
async def upload_syllabus(
    syllabus_board: str = Form(...),
    standard: str = Form(...),
    state: str = Form(...),
    subject: str = Form(...),
    count: int = Form(...),
    syllabus_pdf: UploadFile = File(...)
):

    if syllabus_pdf.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF allowed")

    # Save file
    file_id = str(uuid.uuid4())
    filename = f"{file_id}.pdf"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(await syllabus_pdf.read())

    # Extract text
    text_content = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text_content += (page.extract_text() or "") + "\n"
    except:
        text_content = ""

    # Insert syllabus entry
    data = {
        "board": syllabus_board,
        "standard": standard,
        "state": state,
        "subject": subject,
        "question_count": count,
        "file_path": file_path,
        "text_content": text_content,
        "processed": False,
        "status": "queued",
        "progress": 0,
        "created_at": datetime.utcnow()
    }

    result = await db.syllabus.insert_one(data)

    return {
        "status": "uploaded",
        "syllabus_id": str(result.inserted_id)
    }


# =====================================================================
# 2️⃣ Trigger Processing (returns immediately)
# =====================================================================
@router.post("/process-syllabus/{syllabus_id}")
async def process_syllabus_trigger(syllabus_id: str):

    syllabus = await db.syllabus.find_one({"_id": ObjectId(syllabus_id)})
    if not syllabus:
        raise HTTPException(status_code=404, detail="Syllabus not found")

    # Run worker in background (ASYNC)
    asyncio.create_task(process_syllabus_worker(syllabus_id))

    return {
        "status": "started",
        "message": "Processing started in background",
        "syllabus_id": syllabus_id
    }


# =====================================================================
# 3️⃣ Background Worker (async)
# =====================================================================
async def process_syllabus_worker(syllabus_id: str):

    # Update status → Extracting structure
    await db.syllabus.update_one(
        {"_id": ObjectId(syllabus_id)},
        {"$set": {"status": "extracting", "progress": 10}}
    )

    syllabus = await db.syllabus.find_one({"_id": ObjectId(syllabus_id)})
    text = syllabus.get("text_content", "")

    prompt = f"""
You are an expert syllabus analyzer for Kerala SCERT textbooks.
Your job is to extract accurate chapter titles and content from the provided syllabus text.

Rules:
- Identify REAL chapter names exactly as they appear.
- Maintain syllabus order.
- Do NOT invent or modify chapter titles.
- Group all relevant remaining text under its chapter.

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
        ai = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        raw = ai.choices[0].message.content
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        chapters = json.loads(cleaned)
        # Save chapter titles in main syllabus table
        chapter_titles = [c["chapter"].strip() for c in chapters]
        await db.syllabus.update_one(
            {"_id": ObjectId(syllabus_id)},
            {"$set": {"chapters": chapter_titles}}
        )

    except Exception as e:
        await db.syllabus.update_one(
            {"_id": ObjectId(syllabus_id)},
            {"$set": {"status": "failed", "progress": 0}}
        )
        return

    # Update progress → Embeddings
    await db.syllabus.update_one(
        {"_id": ObjectId(syllabus_id)},
        {"$set": {"status": "embedding", "progress": 40}}
    )

    # ---- EMBEDDINGS AND STORAGE ----
    for idx, ch in enumerate(chapters):
        try:
            emb = client.embeddings.create(
                model="text-embedding-3-large",
                input=ch["content"]
            )
            vector = emb.data[0].embedding

            chapter_doc = {
                "syllabus_id": syllabus_id,
                "board": syllabus["board"],
                "standard": syllabus["standard"],
                "state": syllabus["state"],
                "subject": syllabus["subject"],
                "chapter_title": ch["chapter"].strip(),
                "content": ch["content"].strip(),
                "vector": vector,
                "created_at": datetime.utcnow(),
            }

            await db.syllabus_chapters.insert_one(chapter_doc)

            progress = 40 + int((idx + 1) / len(chapters) * 55)
            await db.syllabus.update_one(
                {"_id": ObjectId(syllabus_id)},
                {"$set": {"progress": progress}}
            )

        except:
            pass

    await db.syllabus.update_one(
        {"_id": ObjectId(syllabus_id)},
        {"$set": {
            "status": "completed",
            "processed": True,
            "progress": 100
        }}
    )


# =====================================================================
# 4️⃣ STATUS ENDPOINT (poll every 2s)
# =====================================================================
@router.get("/syllabus/status/{syllabus_id}")
async def syllabus_status(syllabus_id: str):

    data = await db.syllabus.find_one({"_id": ObjectId(syllabus_id)})
    if not data:
        raise HTTPException(status_code=404, detail="Invalid ID")

    data["_id"] = str(data["_id"])
    return data



from fastapi import Body


# ============================
# 1) GET standards (distinct)
# ============================
@router.get("/standards")
async def get_standards():
    # returns list of unique standards (as strings) sorted
    standards = await db.syllabus.distinct("standard")
    # normalize to strings and sort numeric where possible
    try:
        standards_sorted = sorted(standards, key=lambda x: int(x))
    except:
        standards_sorted = sorted(standards)
    return {"standards": standards_sorted}


# ============================
# 2) GET subjects for a standard
# ============================
@router.get("/subjects/{standard}")
async def get_subjects(standard: str):
    subjects = await db.syllabus.distinct("subject", {"standard": standard})
    subjects = sorted([s for s in subjects if s])  # filter empty
    return {"subjects": subjects}


# ===============================================
# 3) GET chapters for a given standard + subject
# ===============================================
@router.get("/chapters/{standard}/{subject}")
async def get_chapters(standard: str, subject: str):
    # First try to read 'chapters' array from syllabus documents
    docs = await db.syllabus.find({"standard": standard, "subject": subject, "processed": True}).to_list(None)

    chapter_set = []
    for d in docs:
        chs = d.get("chapters")
        if isinstance(chs, list):
            for c in chs:
                if c and c not in chapter_set:
                    chapter_set.append(c)

    # Fallback: if nothing in 'chapters' arrays, use syllabus_chapters collection
    if not chapter_set:
        ch_docs = await db.syllabus_chapters.find({"standard": standard, "subject": subject}).to_list(None)
        for cd in ch_docs:
            title = cd.get("chapter_title")
            if title and title not in chapter_set:
                chapter_set.append(title)

    return {"chapters": chapter_set}


# =====================================================
# 4) POST generate-questions (trigger background worker)
# =====================================================
@router.post("/generate-questions")
async def generate_questions_trigger(payload: dict = Body(...)):
    """
    payload example:
    {
      "standard": "10",
      "subject": "Biology",
      "chapters": ["Paths of Evolution","Behind Sensations"],
      "papers": 2,
      "marks": 50
    }
    """
    standard = payload.get("standard")
    subject = payload.get("subject")
    chapters = payload.get("chapters", [])
    papers = int(payload.get("papers", 1))
    marks = int(payload.get("marks", 50))

    if not standard or not subject or not chapters:
        raise HTTPException(status_code=400, detail="standard, subject and chapters are required")

    job_id = str(uuid.uuid4())
    job_doc = {
        "job_id": job_id,
        "standard": standard,
        "subject": subject,
        "chapters": chapters,
        "papers": papers,
        "marks": marks,
        "status": "queued",
        "progress": 0,
        "created_at": datetime.utcnow()
    }
    await db.question_jobs.insert_one(job_doc)

    # start background worker
    asyncio.create_task(generate_questions_worker(job_id))

    return {"status": "started", "job_id": job_id}





# =====================================================
# Background worker: generate_questions_worker
# =====================================================


# =====================================================
# Blueprint functions
# =====================================================

def get_exam_structure(std: int, total: int):
    """Return allowed types and blueprint sections for exam based on standard."""
    structure = {
        1: (["MCQ", "FillInTheBlanks", "MatchTheFollowing", "TrueFalse", "PictureBased"],  {"A": (1, 25)}),
        2: (["MCQ", "FillInTheBlanks", "MatchTheFollowing", "TrueFalse", "PictureBased", "VeryShort"], {"A": (1, 15), "B": (2, 5)}),
        3: (["MCQ", "FillInTheBlanks", "MatchTheFollowing", "TrueFalse", "PictureBased", "VeryShort"], {"A": (1, 15), "B": (2, 5)}),
        4: (["MCQ", "FillInTheBlanks", "TrueFalse", "VeryShort", "Short"], {"A": (1, 10), "B": (2, 5), "C": (3, 2)}),
        5: (["MCQ", "FillInTheBlanks", "TrueFalse", "VeryShort", "Short", "PictureBased"], {"A": (1, 15), "B": (2, 5), "C": (4, 2)}),
        6: (["MCQ", "VeryShort", "Short"], {"A": (1, 10), "B": (2, 5), "C": (4, 2)}),
        7: (["MCQ", "VeryShort", "Short", "ShortEssay"], {"A": (1, 10), "B": (2, 10), "C": (3, 4), "D": (5, 2)}),
        8: (["MCQ", "VeryShort", "Short", "ShortEssay"], {"A": (1, 10), "B": (2, 10), "C": (3, 4), "D": (5, 2)}),
    }

    if std in [9, 10]:
        if total == 50:
            structure[std] = (["MCQ", "VeryShort", "Short", "Essay", "Apply", "Analyze"],
                              {"A": (1, 5), "B": (2, 5), "C": (3, 3), "D": (8, 2), "E": (10, 1)})
        else:
            structure[std] = (["MCQ", "VeryShort", "Short", "Essay", "Apply", "Analyze"],
                              {"A": (1, 10), "B": (2, 10), "C": (3, 6), "D": (5, 4), "E": (8, 2)})

    if std == 11:
        structure[11] = (["MCQ", "Short", "Essay", "Apply", "Analyze", "CaseStudy", "Diagram"],
                         {"A": (1, 5), "B": (3, 5), "C": (8, 3), "D": (10, 1)} if total == 50 else
                         {"A": (1, 10), "B": (3, 6), "C": (5, 4), "D": (8, 2), "E": (10, 1)})

    if std == 12:
        structure[12] = (["MCQ", "Short", "Essay", "Apply", "Analyze", "CaseStudy", "Diagram"],
                         {"A": (1, 10), "B": (4, 5), "C": (10, 2)} if total == 50 else
                         {"A": (1, 15), "B": (3, 8), "C": (5, 3), "D": (8, 3), "E": (10, 1)})

    return structure.get(std, structure[12])


def build_distribution_from_structure(sections):
    distribution = []
    for sec, (mark, count) in sections.items():
        distribution.extend([mark] * count)
    return distribution


# =====================================================
# Generate single paper
# =====================================================

async def generate_single_paper(job, idx, allowed_types, sections, distribution):
    std = int(job["standard"])
    subject = job["subject"]
    chapters = job["chapters"]
    total_marks = int(job["marks"])
    job_id = job["job_id"]

    prompt = f"""
Generate Kerala SCERT format question paper:

Standard: {std}
Subject: {subject}
Chapters: {', '.join(chapters)}
Required Total Marks: {total_marks}

Allowed Question Types:
{allowed_types}

Sections and Mark Pattern:
{json.dumps(sections)}

Marks distribution in exact order:
{distribution}

Rules:
- Follow order of marks EXACTLY in questions list.
- Include a realistic mix of question types based on SCERT style.
- Strict JSON only, no text outside JSON.

Expected Format:
{{
 "paper_id": "{job_id}-{idx}",
 "standard": "{std}",
 "subject": "{subject}",
 "marks_total": {total_marks},
 "sections": {json.dumps(sections)},
 "questions": [
   {{"type":"MCQ", "question":"Example?", "marks":1}}
 ]
}}
"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    raw = resp.choices[0].message.content
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    paper_json = json.loads(cleaned)

    res = await db.generated_papers.insert_one({
        "job_id": job_id,
        "paper_index": idx,
        "paper": paper_json,
        "created_at": datetime.utcnow()
    })

    return str(res.inserted_id)


# =====================================================
# Main worker
# =====================================================

async def generate_questions_worker(job_id: str):
    job = await db.question_jobs.find_one({"job_id": job_id})
    if not job:
        return

    await db.question_jobs.update_one({"job_id": job_id}, {"$set": {"status": "running", "progress": 5}})

    std = int(job["standard"])
    total_marks = int(job["marks"])
    papers = job["papers"]

    allowed_types, sections = get_exam_structure(std, total_marks)
    distribution = build_distribution_from_structure(sections)

    generated_ids = []

    tasks = [
        generate_single_paper(job, i + 1, allowed_types, sections, distribution)
        for i in range(papers)
    ]

    for idx, task in enumerate(asyncio.as_completed(tasks), start=1):
        rid = await task
        generated_ids.append(rid)

        await db.question_jobs.update_one({"job_id": job_id},
                                          {"$set": {"progress": int(idx / papers * 100)}})

    await db.question_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "completed", "generated": generated_ids, "progress": 100}}
    )

    logging.info(f"Job {job_id} completed")


from typing import List, Optional



    # Job status
@router.get("/question-job-status/{job_id}")
async def question_job_status(job_id: str):
    job = await db.question_jobs.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "progress": job.get("progress", 0),
        "message": job.get("message", "")
    }

# Fetch generated papers (filter by job_id)
@router.get("/generated-papers")
async def get_generated_papers(job_id: Optional[str] = None):
    q = {}
    if job_id:
        q["job_id"] = job_id
    docs = await db.generated_papers.find(q).to_list(None)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs