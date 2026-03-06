
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

def normalize_text(text: str) -> str:
    """Collapses characters separated by spaces and artifacts like 'WWeeaatthheerr'."""
    if not text: return ""
    import re
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

def validate_fix_marks(paper: dict, required_total: int):
    total = sum(q.get("marks", 0) for q in paper["questions"])
    diff = required_total - total
    if diff != 0 and paper["questions"]:
        paper["questions"][-1]["marks"] += diff
    return paper


@router.post("/upload-chapter", dependencies=[Depends(get_current_admin)])
async def upload_chapter_endpoint(
    background_tasks: BackgroundTasks,
    board: str = Form(...),
    standard: str = Form(...),
    state: str = Form(...),
    subject: str = Form(...),
    chapter_name: str = Form(...),
    chapter_number: str = Form(...),
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
    try:
        print(f"[BG-CHAPTER] Processing: {full_chapter_title} ({original_filename})")
        
        # 1. Extract Text
        text_content = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text_content += (page.extract_text() or "") + "\n"
        
        text_content = normalize_text(text_content)
        if not text_content.strip():
            print(f"[BG-CHAPTER] Error: No text extracted from {file_path}")
            return

        # 2. Get Textbook ID
        textbook_doc = await db.textbook.find_one(textbook_query)
        if not textbook_doc:
            print(f"[BG-CHAPTER] Error: Textbook container not found for {textbook_query}")
            return
        textbook_id = str(textbook_doc["_id"])

        # 3. Generate Embeddings & Save Passages
        PASSAGE_SIZE = 4000
        PASSAGE_OVERLAP = 400
        passages = []
        
        if len(text_content) <= PASSAGE_SIZE:
            passages.append(text_content)
        else:
            for i in range(0, len(text_content), PASSAGE_SIZE - PASSAGE_OVERLAP):
                passages.append(text_content[i:i + PASSAGE_SIZE])

        valid_docs = []
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
            print(f"[BG-CHAPTER] SUCCESS: '{full_chapter_title}' processed with {len(valid_docs)} passages.")

    except Exception as e:
        print(f"[BG-CHAPTER] CRITICAL WORKER ERROR: {e}")
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
# ROUTES - TEXTBOOK & CHAPTER MANAGEMENT
# --------------------------

@router.get("/textbooks", dependencies=[Depends(get_current_admin)])
async def get_all_textbooks():
    """Fetch all uploaded textbooks and their generated chapters."""
    textbooks = await db.textbook.find({}).sort("created_at", -1).to_list(None)
    for t in textbooks:
        t["_id"] = str(t["_id"])
    return {"textbooks": textbooks}

@router.delete("/textbook/{textbook_id}/chapter/{chapter_name}", dependencies=[Depends(get_current_admin)])
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
    chapter_docs = await db.textbook_chapters.find({
        "standard": str(std),
        "subject": subject,
        "chapter_title": {"$in": chapters}
    }).sort("passage_index", 1).to_list(None)

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

            prompt = f"""
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
                temperature=0.7  # Higher temperature = more creative variation across papers
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
            try:
                # Inject metadata for PDF header
                paper_json["marks"] = total_marks
                paper_json["standard"] = str(std)
                paper_json["subject"] = subject
                paper_json["time"] = "TIME - 90 MINUTES" if total_marks >= 50 else "TIME - 45 MINUTES"

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

