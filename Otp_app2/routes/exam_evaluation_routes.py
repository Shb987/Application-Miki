import uuid
import os
import re
import datetime
import base64
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from openai import AsyncOpenAI
import json
from bson import ObjectId

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

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
        response = await client.chat.completions.create(
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
async def evaluate_answer(question, student_answer, max_marks, context_text):
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
        response = await client.chat.completions.create(
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
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import JSONResponse
from typing import List
import os, uuid, datetime

from utils.user_auth import get_current_user
from services.notification_service import create_notification

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from typing import List
import os
import uuid
import datetime

from utils.user_auth import get_current_user
from services.notification_service import create_notification
from bson import ObjectId

def clean_mongo(data):
    if isinstance(data, dict):
        return {k: clean_mongo(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_mongo(v) for v in data]
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data

async def process_evaluation_background(evaluation_id: str, paper_id: str, student_id: str, saved_file_paths: List[str]):
    evaluation_status = "FAILED"
    total_score = 0
    max_total = 0

    try:
        # 2. Fetch paper
        paper_doc = await db.generated_papers.find_one({"paper.paper_id": paper_id})
        if not paper_doc:
            raise Exception("Question paper not found")

        paper = paper_doc["paper"]

        # 3. Prepare question context
        question_paper_text = ""
        q_counter = 1
        for section in paper["sections"]:
            for q in section["questions"]:
                question_paper_text += f"{q_counter}. {q['question']}\n"
                q_counter += 1

        # 4. OCR
        student_answers_json = await extract_answers_with_vision(
            saved_file_paths,
            question_paper_text
        )

        student_answers = {str(k): v for k, v in student_answers_json.items()}

        # 5. Context
        chapter_docs = await db.textbook_chapters.find({
            "standard": str(paper.get("standard")),
            "subject": paper.get("subject"),
            "chapter_title": {"$in": paper.get("chapters_used", [])}
        }).to_list(None)

        context_text = "".join(
            f"\n=== {doc.get('chapter_title')} ===\n{doc.get('content','')[:50000]}"
            for doc in chapter_docs
        ) or "Evaluate using general academic knowledge."

        # 6. Evaluation
        detailed_results = []
        q_number = 1

        for section in paper["sections"]:
            marks = section["marks_per_question"]
            for q in section["questions"]:
                student_ans = student_answers.get(str(q_number), "[Not Attempted]")
                eval_result = await evaluate_answer(
                    q["question"], student_ans, marks, context_text
                )

                score = float(str(eval_result.get("score", "0")).split("/")[0])
                total_score += score
                max_total += marks

                detailed_results.append({
                    "q_no": q_number,
                    "question": q["question"],
                    "student_answer": student_ans,
                    "max_marks": marks,
                    "score": score,
                    "feedback": eval_result.get("feedback"),
                    "ideal_answer": eval_result.get("ideal_answer")
                })

                q_number += 1

        evaluation_status = "COMPLETED"

        # Update the existing evaluation record
        await db.evaluations.update_one(
            {"evaluation_id": evaluation_id},
            {
                "$set": {
                    "status": evaluation_status,
                    "total_score": total_score,
                    "max_total": max_total,
                    "detailed_results": detailed_results,
                    "completed_at": datetime.datetime.utcnow().isoformat()
                }
            }
        )

    except Exception as e:
        error_message = str(e)
        print(f"Background Evaluation Failed: {e}")
        
        await db.evaluations.update_one(
            {"evaluation_id": evaluation_id},
            {
                "$set": {
                    "status": "FAILED",
                    "error": error_message,
                    "completed_at": datetime.datetime.utcnow().isoformat()
                }
            }
        )

    finally:
        # 🔔 Notification
        try:
            if evaluation_status == "COMPLETED":
                await create_notification(
                    db=db,
                    user_id=student_id,
                    title="Evaluation Completed",
                    message=f"Your evaluation is complete. Score: {total_score}/{max_total}.",
                    notification_type="evaluation_completed"
                )
            else:
                await create_notification(
                    db=db,
                    user_id=student_id,
                    title="Evaluation Failed",
                    message="Evaluation failed. Please try again later.",
                    notification_type="evaluation_failed"
                )
        except Exception as n_err:
            print("Notification error:", n_err)

        # Cleanup files
        for path in saved_file_paths:
            try:
                os.remove(path)
            except:
                pass

@router.post("/evaluate-answersheet")
async def evaluate_answersheet(
    background_tasks: BackgroundTasks,
    student_id: str = Form(...),
    paper_id: str = Form(...),
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    saved_file_paths = []
    evaluation_id = str(uuid.uuid4())
    
    try:
        # 1. Save files locally (must be done in main thread to await UploadFile)
        os.makedirs("temp", exist_ok=True)
        for file in files:
            ext = file.filename.split(".")[-1]
            path = f"temp/{uuid.uuid4()}.{ext}"
            with open(path, "wb") as f:
                f.write(await file.read())
            saved_file_paths.append(path)

        # 2. Create Initial DB Record
        initial_evaluation_data = {
            "evaluation_id": evaluation_id,
            "paper_id": paper_id,
            "student_id": student_id,
            "status": "PROCESSING",
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        await db.evaluations.insert_one(initial_evaluation_data)

        # 3. Add Background Task
        background_tasks.add_task(
            process_evaluation_background,
            evaluation_id,
            paper_id,
            student_id,
            saved_file_paths
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": True,
                "message": "Evaluation started in background.",
                "data": {
                    "evaluation_id": evaluation_id,
                    "status": "PROCESSING"
                }
            }
        )

    except Exception as e:
        # Cleanup if initial setup fails
        for path in saved_file_paths:
            try:
                os.remove(path)
            except:
                pass
                
        return JSONResponse(
            status_code=500,
            content={
                "status": False,
                "message": "Failed to start evaluation",
                "error": str(e)
            }
        )


@router.get("/notifications/{user_id}")
async def get_notifications(user_id: str, current_user: dict = Depends(get_current_user)):
    print(current_user)
    # Enforce ownership: User can only see their own notifications
    user_student_id = current_user.get("student_id")
    print(user_student_id)
    # If the token belongs to a student, ensure it matches the requested user_id
    if user_student_id and user_student_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access to notifications")

    notifications = await db.notifications.find(
        {"user_id": user_id, "is_read": False}
    ).sort("created_at", -1).to_list(100)

    return {"status": True, "data": clean_mongo(notifications)}

@router.post("/notifications/read/{notification_id}")
async def mark_notification_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("student_id")
    print(user_id)
    
    # Update only if notification belongs to the user
    query = {"notification_id": notification_id}
    if user_id:
        query["user_id"] = user_id

    result = await db.notifications.update_one(
        query,
        {"$set": {"is_read": True}}
    )
    
    if result.matched_count == 0:
        return JSONResponse(
            status_code=404,
            content={"status": False, "message": "Notification not found"}
        )

    return {"status": True, "message": "Notification marked as read"}
