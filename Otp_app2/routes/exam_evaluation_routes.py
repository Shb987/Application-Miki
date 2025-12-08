import uuid
import os
import re
import datetime
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from openai import OpenAI
import fitz
from PIL import Image
import io
import json
from bson import ObjectId  # FIX

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

from core.database import db

router = APIRouter()

from typing import List

# -------------------------------
# 1. OCR (UPDATED FOR IMAGES)
# -------------------------------
async def extract_text_from_images(image_paths):
    full_text = ""
    
    # Placeholder: In a real scenario, you'd use OpenAI Vision or an OCR tool here.
    # For now, we'll just iterate and append a placeholder.
    for i, img_path in enumerate(image_paths):
        full_text += f"\n--- Image {i+1} ---\n"
        # TODO: Implement actual OCR here. 
        # Example: 
        # with open(img_path, "rb") as image_file:
        #     response = client.chat.completions.create(...)
        full_text += "[Extracted text placeholder from image]\n"

    return full_text


# --------------------------------
# 2. SPLIT ANSWERS FROM OCR TEXT
# --------------------------------
def split_answers(raw_text):
    pattern = r"(\d+)\.|\bQ(\d+)"
    parts = re.split(pattern, raw_text)

    answers = {}
    q_number = None

    for item in parts:
        if item is None:
            continue
        if item.strip().isdigit():
            q_number = int(item.strip())
        else:
            if q_number:
                answers[q_number] = item.strip()
                q_number = None

    return answers


# --------------------------------
# 3. EVALUATE ONE QUESTION
# --------------------------------
def evaluate_answer(question, student_answer, max_marks):
    prompt = f"""
You are an expert evaluator.

QUESTION:
{question}

STUDENT ANSWER:
{student_answer}

MAX MARKS: {max_marks}

Return JSON only:
{{
  "score": "...",
  "feedback": "...",
  "ideal_answer": "..."
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )

    message = response.choices[0].message.content

    try:
        return json.loads(message)
    except:
        return {
            "score": 0,
            "feedback": "AI response could not be parsed.",
            "ideal_answer": ""
        }


# ------------------------------
# 4. FIX ObjectId Serializer
# ------------------------------
def serialize_mongo(document):
    """Convert ObjectId → str recursively"""
    if isinstance(document, dict):
        return {k: serialize_mongo(v) for k, v in document.items()}
    elif isinstance(document, list):
        return [serialize_mongo(i) for i in document]
    elif isinstance(document, ObjectId):
        return str(document)
    else:
        return document


# ------------------------------
# 5. MAIN API
# ------------------------------
@router.post("/evaluate-answersheet")
async def evaluate_answersheet(
    student_id: str = Form(...),
    paper_id: str = Form(...),
    files: List[UploadFile] = File(...)
):

    # Save files
    saved_file_paths = []
    os.makedirs("temp", exist_ok=True)
    
    for file in files:
        file_ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
        temp_path = f"temp/{uuid.uuid4()}.{file_ext}"
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        saved_file_paths.append(temp_path)

    # OCR extraction
    raw_text = await extract_text_from_images(saved_file_paths)

    # Split answers
    student_answers = split_answers(raw_text)

    # Find question paper
    paper_doc = await db.generated_papers.find_one({"paper.paper_id": paper_id})
    if not paper_doc:
        return JSONResponse({"status": False, "message": "Question paper not found."})

    paper = paper_doc["paper"]

    total_score = 0
    max_total = 0
    detailed_results = []
    q_number = 1

    # Evaluate all sections & questions
    for section in paper["sections"]:
        marks_per_q = section["marks_per_question"]

        for q in section["questions"]:
            question_text = q["question"]
            student_ans = student_answers.get(q_number, "")

            eval_result = evaluate_answer(question_text, student_ans, marks_per_q)

            score_raw = str(eval_result.get("score", "0"))
            if "/" in score_raw:
                score = int(score_raw.split("/")[0])
            else:
                try:
                    score = int(score_raw)
                except:
                    score = 0

            total_score += score
            max_total += marks_per_q

            detailed_results.append({
                "q_no": q_number,
                "question": question_text,
                "student_answer": student_ans,
                "max_marks": marks_per_q,
                "score": score,
                "feedback": eval_result.get("feedback"),
                "ideal_answer": eval_result.get("ideal_answer")
            })

            q_number += 1

    evaluation_data = {
        "evaluation_id": str(uuid.uuid4()),
        "paper_id": paper_id,
        "student_id": student_id,
        "total_score": total_score,
        "max_total": max_total,
        "detailed_results": detailed_results,
        "created_at": datetime.datetime.utcnow().isoformat()
    }

    # Save to DB
    await db.evaluations.insert_one(evaluation_data)

    # Serialize to remove ObjectId
    safe_data = serialize_mongo(evaluation_data)

    return JSONResponse({
        "status": True,
        "message": "Evaluation completed successfully.",
        "data": safe_data
    })
