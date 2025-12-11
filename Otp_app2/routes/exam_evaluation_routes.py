import uuid
import os
import re
import datetime
import base64
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from openai import OpenAI
import json
from bson import ObjectId

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

from core.database import db

router = APIRouter()

from typing import List

# -------------------------------
# 1. OCR WITH GPT-4o VISION
# -------------------------------
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

async def extract_answers_with_vision(image_paths, question_paper_text):
    """
    Sends images to GPT-4o to extract handwritten answers directly into JSON.
    """
    
    content_payload = [
        {
            "type": "text", 
            "text": f"""
            You are an expert OCR assistant for handwritten exam papers.
            
            ### EXAM QUESTIONS (CONTEXT) ###
            {question_paper_text}
            ### END QUESTIONS ###

            TASK:
            1. Read the handwritten answers from the provided images.
            2. Match each answer to the correct Question Number from the "EXAM QUESTIONS" list above based on the content.
               - IGNORE the student's handwritten numbering if it conflicts with the content of the answer.
               - Use the content to determine which question is being answered.
            3. Extract the full text of the answer.
            
            OUTPUT FORMAT:
            Return a STRICT JSON object where keys are Question Numbers (as integers) and values are the Answer Text.
            
            Example:
            {{
                "1": "The cell is the basic unit of life...",
                "2": "Photosynthesis is the process..."
            }}
            
            If you cannot read an answer, mark it as "[Unreadable]".
            """
        }
    ]

    for img_path in image_paths:
        base64_image = encode_image(img_path)
        content_payload.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}",
                "detail": "high"
            }
        })

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": content_payload}
            ],
            max_tokens=4000,
            response_format={"type": "json_object"}
        )
        
        result = response.choices[0].message.content
        return json.loads(result)
    except Exception as e:
        print(f"OCR Failed: {e}")
        return {}

# --------------------------------
# 2. EVALUATE ONE QUESTION (RAG)
# --------------------------------
def evaluate_answer(question, student_answer, max_marks, context_text):
    prompt = f"""
You are an expert academic evaluator.

### REFERENCE MATERIAL (TEXTBOOK CONTENT) ###
{context_text}
### END REFERENCE ###

QUESTION:
{question}

STUDENT ANSWER:
{student_answer}

MAX MARKS: {max_marks}

TASK:
Evaluate the student's answer based STRICTLY on the provided REFERENCE MATERIAL.
- If the answer is correct according to the text, award full marks.
- If partially correct, award partial marks.
- If the answer contradicts the text, award 0.

Return JSON only:
{{
  "score": "number (e.g. 2, 0.5, 5)",
  "feedback": "Brief feedback explaining the score",
  "ideal_answer": "The correct answer based on the reference text"
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        message = response.choices[0].message.content
        return json.loads(message)
    except:
        return {
            "score": 0,
            "feedback": "AI evaluation failed.",
            "ideal_answer": ""
        }


# ------------------------------
# 3. UTILS
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
# 4. MAIN API
# ------------------------------
@router.post("/evaluate-answersheet")
async def evaluate_answersheet(
    student_id: str = Form(...),
    paper_id: str = Form(...),
    files: List[UploadFile] = File(...)
):

    # 1. Save files locally
    saved_file_paths = []
    os.makedirs("temp", exist_ok=True)
    
    for file in files:
        file_ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
        temp_path = f"temp/{uuid.uuid4()}.{file_ext}"
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        saved_file_paths.append(temp_path)

    # 2. Find question paper (MOVED UP)
    paper_doc = await db.generated_papers.find_one({"paper.paper_id": paper_id})
    if not paper_doc:
        return JSONResponse({"status": False, "message": "Question paper not found."})

    paper = paper_doc["paper"]
    standard = paper.get("standard")
    subject = paper.get("subject")
    chapters_used = paper.get("chapters_used", [])

    # Construct Question Paper Text for Context
    question_paper_text = ""
    q_counter = 1
    for section in paper["sections"]:
        for q in section["questions"]:
            question_paper_text += f"{q_counter}. {q['question']}\n"
            q_counter += 1

    # 3. OCR extraction (Vision) - Now with Context
    student_answers_json = await extract_answers_with_vision(saved_file_paths, question_paper_text)
    
    # Normalize keys to strings for easy lookup
    student_answers = {str(k): v for k, v in student_answers_json.items()}

    # 4. RAG: Fetch Textbook Content
    chapter_docs = await db.textbook_chapters.find({
        "standard": str(standard),
        "subject": subject,
        "chapter_title": {"$in": chapters_used}
    }).to_list(None)

    context_text = ""
    for doc in chapter_docs:
        # Limit context to avoid overflow (approx 50k chars total context)
        content_snippet = doc.get("content", "")[:50000]
        context_text += f"\n=== CHAPTER: {doc.get('chapter_title')} ===\n{content_snippet}\n"
    
    if not context_text:
        context_text = "No specific textbook content found. Evaluate based on general academic knowledge."

    total_score = 0
    max_total = 0
    detailed_results = []
    q_number = 1

    # 5. Evaluate all sections & questions
    for section in paper["sections"]:
        marks_per_q = section["marks_per_question"]

        for q in section["questions"]:
            question_text = q["question"]
            
            # Try to find answer by Question Number
            student_ans = student_answers.get(str(q_number))
            
            # If not found, try finding by text match (fallback) or just mark as not attempted
            if not student_ans:
                student_ans = "[Not Attempted / Not Detected]"

            eval_result = evaluate_answer(question_text, student_ans, marks_per_q, context_text)

            # Parse score safely
            score_raw = str(eval_result.get("score", "0"))
            try:
                # Handle cases like "2/5" or "2.5"
                if "/" in score_raw:
                    score = float(score_raw.split("/")[0])
                else:
                    score = float(score_raw)
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

    # 6. Save to DB
    await db.evaluations.insert_one(evaluation_data)

    # 7. Cleanup Temp Files
    for path in saved_file_paths:
        try:
            os.remove(path)
        except:
            pass

    # Serialize to remove ObjectId
    safe_data = serialize_mongo(evaluation_data)

    return JSONResponse({
        "status": True,
        "message": "Evaluation completed successfully.",
        "data": safe_data
    })


