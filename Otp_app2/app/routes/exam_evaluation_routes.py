import uuid
import os
import re
import datetime
import base64
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, Query, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from dotenv import load_dotenv
from openai import AsyncOpenAI
import json
from bson import ObjectId
import difflib
from app.core.database import db
from typing import List, Tuple, Dict, Any, Optional
from app.utils.user_auth import get_current_user
from app.services.notification_service import create_notification
from app.utils.usage_guard import check_and_use_quota


# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or "sk-placeholder"

client = AsyncOpenAI(api_key=OPENAI_API_KEY)
router = APIRouter()


# -------------------------------
# 1. OCR WITH GPT-4o VISION
# -------------------------------
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def is_invalid_or_unattempted_answer(student_answer: str) -> Tuple[bool, str]:
    """
    Checks if a student answer string is missing, unattempted, unreadable, 
    or a non-academic placeholder (e.g. 'JPG', file name, random punctuation).
    """
    if student_answer is None or not isinstance(student_answer, str):
        return True, "No answer was provided for this question."
    
    cleaned = student_answer.strip()
    lower_cleaned = cleaned.lower()

    if not lower_cleaned:
        return True, "No answer was provided for this question."

    # Immediate match against common non-attempt / unreadable / placeholder tokens
    unattempted_tokens = {
        "[not attempted]", "not attempted", "[unreadable]", "unreadable",
        "[invalid answersheet]", "invalid answersheet", "none", "n/a", "na",
        "no answer", "nil", "null", "blank", "unanswered", "empty",
        "jpg", "jpeg", "png", "gif", "svg", "pdf", "image", "file", "icon",
        "thumbnail", "placeholder", "document"
    }
    if lower_cleaned in unattempted_tokens:
        return True, "No valid answer provided (unattempted, unreadable, or placeholder)."

    # Remove non-alphanumeric characters
    alpha_chars = re.sub(r'[^a-zA-Z]', '', lower_cleaned)
    
    # If the text has fewer than 2 letters and is not "yes" or "no"
    if len(alpha_chars) < 2 and lower_cleaned not in ["yes", "no"]:
        return True, "Answer contains no meaningful content or is too short to evaluate."
        
    # Check if the answer is just file extensions or image words like "jpg file"
    if alpha_chars in ["jpg", "jpeg", "png", "gif", "svg", "pdf", "jpgfile", "jpegfile", "imagefile"]:
        return True, "Answer is a file extension / placeholder label rather than student work."

    return False, ""


async def extract_answers_with_vision(image_paths, question_paper_text, student_id: str) -> dict:
    """
    Sends images to GPT-4o Vision to extract handwritten answers directly into structured data.
    Validates whether the image is actually a valid student exam answersheet.
    """
    content_payload = [
        {
            "type": "text", 
            "text": f"""
You are a strict, objective document verification and OCR assistant for school exam papers.

### EXAM QUESTIONS (CONTEXT FOR MATCHING ONLY) ###
{question_paper_text}
### END QUESTIONS ###

CRITICAL RULES:
1. DOCUMENT VALIDITY CHECK:
   - Determine whether the provided image(s) show a genuine student exam paper, handwritten answer sheet, or notebook with student answers.
   - If the image is a generic file icon (such as a placeholder 'JPG' or 'PNG' document icon), a logo, computer icon, landscape, meme, random object, blank image, or contains NO handwritten student exam answers, you MUST set "is_valid_answersheet": false.
2. DO NOT ANSWER THE QUESTIONS:
   - You are STRICTLY a mechanical OCR transcriber.
   - NEVER generate, invent, summarize, or solve the questions yourself.
   - ONLY transcribe text that is physically written by the student on the page.
   - If a question is not answered on the page, set its value to "[Not Attempted]" or omit it.
3. UNREADABLE OR PLACEHOLDER TEXT:
   - Do not transcribe image metadata, file extensions like 'JPG', or computer UI text as student answers.
   - If handwritten text is illegible, mark it as "[Unreadable]".

OUTPUT FORMAT (STRICT JSON OBJECT):
{{
  "is_valid_answersheet": true or false,
  "invalid_reason": "Provide reason if false (e.g. 'Uploaded image is a generic file placeholder icon, not an exam paper'), otherwise empty string",
  "answers": {{
    "1": "transcribed answer for Q1...",
    "2": "[Not Attempted]"
  }}
}}
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
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": content_payload}
            ],
            max_tokens=4000,
            response_format={"type": "json_object"}
        )
        
        # Log usage
        if hasattr(response, 'usage') and response.usage:
            from app.utils.ai_usage_logger import log_ai_usage
            await log_ai_usage(student_id, "Exam Evaluation - OCR", "gpt-4o-mini", response.usage)
            
        result = response.choices[0].message.content
        parsed = json.loads(result)

        is_valid = parsed.get("is_valid_answersheet", True)
        invalid_reason = parsed.get("invalid_reason", "")
        
        if "answers" in parsed and isinstance(parsed["answers"], dict):
            raw_answers = parsed["answers"]
        else:
            raw_answers = {k: v for k, v in parsed.items() if k not in ["is_valid_answersheet", "invalid_reason"]}
            
        # Extra safety check: verify if any extracted answer has meaningful content
        has_any_meaningful_answer = False
        for k, ans in raw_answers.items():
            is_inv, _ = is_invalid_or_unattempted_answer(str(ans))
            if not is_inv:
                has_any_meaningful_answer = True
                break
        
        if not raw_answers or not has_any_meaningful_answer:
            is_valid = False
            if not invalid_reason:
                invalid_reason = "No handwritten or valid student answers could be detected on the uploaded image."
                
        return {
            "is_valid_answersheet": is_valid,
            "invalid_reason": invalid_reason,
            "answers": raw_answers
        }
    except Exception as e:
        print(f"OCR Failed: {e}")
        return {
            "is_valid_answersheet": False,
            "invalid_reason": f"OCR processing failed: {str(e)}",
            "answers": {}
        }


# --------------------------------
# 2. EVALUATE ONE QUESTION (RAG)
# --------------------------------
async def evaluate_answer(question, student_answer, max_marks, context_text, student_id: str, model: str = "gpt-4o-mini"):
    # 🚨 PRE-CHECK: If the answer is unattempted, unreadable, blank, or placeholder,
    # award exactly 0 marks deterministically without wasting AI tokens or risking hallucinations.
    is_invalid, invalid_feedback = is_invalid_or_unattempted_answer(student_answer)
    if is_invalid:
        return {
            "score": 0.0,
            "feedback": invalid_feedback,
            "ideal_answer": "No valid answer submitted to evaluate against textbook reference."
        }

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
- Award marks strictly based on factual correctness according to the reference material.
- If the answer is completely correct, award {max_marks}.
- If partially correct, award partial marks strictly proportional to the valid factual points made.
- If the answer is wrong, contradicts the text, is irrelevant, gibberish, filler, or merely repeats the question, award 0.
- NEVER award default, base, or sympathy marks for incorrect, irrelevant, or non-responsive answers.
- Score MUST be a numeric value between 0 and {max_marks}.

Return JSON only:
{{
  "score": "number between 0 and {max_marks}",
  "feedback": "Brief feedback explaining the score",
  "ideal_answer": "The correct answer based on the reference text"
}}
"""

    MAX_RETRIES = 2
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            # Log usage
            if hasattr(response, 'usage') and response.usage:
                from app.utils.ai_usage_logger import log_ai_usage
                await log_ai_usage(student_id, "Exam Evaluation - Grading", model, response.usage)

            message = response.choices[0].message.content
            parsed = json.loads(message)
            raw_score = parsed.get("score", 0)
            try:
                score_val = float(str(raw_score).split("/")[0].strip())
            except:
                score_val = 0.0
            
            # Clamp score between 0 and max_marks
            parsed["score"] = max(0.0, min(float(max_marks), score_val))
            return parsed

        except Exception as e:
            last_error = str(e)
            print(f"[Grading] Attempt {attempt + 1} failed for question '{question[:60]}': {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1.5 * (attempt + 1))  # 1.5s, then 3s backoff

    print(f"[Grading] All {MAX_RETRIES + 1} attempts failed. Last error: {last_error}")
    return {
        "score": 0.0,
        "feedback": f"AI evaluation failed after {MAX_RETRIES + 1} attempts.",
        "ideal_answer": "",
        "grading_error": True
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


def clean_mongo(data):
    if isinstance(data, dict):
        return {k: clean_mongo(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_mongo(v) for v in data]
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data


def _grade_from_pct(pct: float) -> str:
    if pct >= 85: return "A"
    if pct >= 70: return "B"
    if pct >= 50: return "C"
    return "D"


def _question_status(score: float, max_marks: float, student_answer: str) -> str:
    if not student_answer or "[Not Attempted" in student_answer or student_answer.strip() in ["[Not Attempted]", "Not Attempted", "[Unreadable]", "[Invalid Answersheet]"]:
        return "not_attempted"
    if score == max_marks and max_marks > 0:
        return "correct"
    if score > 0:
        return "partial"
    return "wrong"


def calculate_section_performance(paper_sections: list, detailed_results: list) -> dict:
    """
    Groups detailed_results by section letter using paper_sections boundaries.
    Returns per-section score, max, and percentage.
    """
    section_map = {}  # section_letter -> list of q_no
    q_counter = 1
    for sec in paper_sections:
        letter = sec.get("section", "?")
        marks_per_q = sec.get("marks_per_question", 0)
        count = len(sec.get("questions", []))
        section_map[letter] = {
            "label": f"Section {letter}",
            "marks_per_q": marks_per_q,
            "q_nos": list(range(q_counter, q_counter + count)),
            "score": 0.0,
            "max": marks_per_q * count,
            "pct": 0.0
        }
        q_counter += count

    # Map q_no back to section and accumulate score
    q_to_section = {}
    for letter, info in section_map.items():
        for qno in info["q_nos"]:
            q_to_section[qno] = letter

    for result in detailed_results:
        qno = result.get("q_no")
        sec_letter = q_to_section.get(qno)
        if sec_letter and sec_letter in section_map:
            section_map[sec_letter]["score"] += result.get("score", 0)

    # Calculate percentages, drop internal q_nos list
    output = {}
    for letter, info in section_map.items():
        max_val = info["max"]
        score = round(info["score"], 2)
        pct = round((score / max_val * 100) if max_val > 0 else 0.0, 1)
        output[letter] = {
            "label": info["label"],
            "marks_per_q": info["marks_per_q"],
            "score": score,
            "max": max_val,
            "pct": pct
        }
    return output


async def analyze_topic_strengths(
    detailed_results: list,
    chapters_used: list,
    subject: str,
    student_id: str
) -> dict:
    """
    Uses GPT-4o-mini to analyze strong/weak chapters and topics
    from the evaluated questions. Chapters are the exact ones from the paper.
    """
    # Build compact Q&A summary for the prompt
    qa_summary = ""
    for r in detailed_results:
        qa_summary += (
            f"Q{r['q_no']} ({r['max_marks']}marks): {r['question']}\n"
            f"  Score: {r['score']}/{r['max_marks']} | Answer: {r['student_answer'][:120]}\n\n"
        )

    chapters_list = "\n".join(f"- {c}" for c in chapters_used)

    prompt = f"""
You are an academic performance analyst for school students.

Subject: {subject}
Chapters covered in this exam:
{chapters_list}

Student's evaluated answers:
{qa_summary}

TASK:
1. Map EACH question to the MOST LIKELY chapter from the list above (use exact chapter names).
2. Calculate per-chapter performance (sum scores / sum max_marks for that chapter's questions).
3. Identify specific sub-topics within chapters that are strong or weak.
4. Identify the primary skill gap (recall / understanding / application / analysis).
5. Give 2-3 specific, actionable recommendations.
6. Generate a 3-5 question "Micro-Quiz" (multiple choice) based EXACTLY on the student's weak areas to help them practice.

Return STRICT JSON only:
{{
  "chapter_performance": {{
    "Chapter Name": {{"questions": [1,2,3], "score": 4.0, "max": 5, "pct": 80.0, "strength": "strong"}}
  }},
  "strong_areas": ["specific subtopic 1", "specific subtopic 2"],
  "weak_areas": ["specific subtopic 3"],
  "skill_gap": "one clear sentence describing the skill gap",
  "recommendations": ["recommendation 1", "recommendation 2"],
  "weakness_quiz": [
    {{
      "question": "A specific question testing a weak area...",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_answer": "The exact string from options that is correct",
      "explanation": "Brief explanation of why it's correct"
    }}
  ]
}}

Strength classification: "strong" if pct >= 75, "average" if pct >= 50, "weak" if pct < 50.
If all questions were "[Not Attempted]", reflect that honestly.
"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        if hasattr(response, 'usage') and response.usage:
            from app.utils.ai_usage_logger import log_ai_usage
            await log_ai_usage(student_id, "Exam Evaluation - Topic Analysis", "gpt-4o-mini", response.usage)

        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[Topic Analysis] Failed: {e}")
        return {
            "chapter_performance": {},
            "strong_areas": [],
            "weak_areas": [],
            "skill_gap": "Analysis unavailable.",
            "recommendations": [],
            "weakness_quiz": []
        }


# ------------------------------
# 4. MAIN API
# ------------------------------

async def process_evaluation_background(eval_oid: str, paper_id: str, student_id: str, saved_file_paths: List[str], model: str = "gpt-4o-mini"):
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
        ocr_result = await extract_answers_with_vision(
            saved_file_paths,
            question_paper_text,
            student_id
        )

        is_valid_paper = ocr_result.get("is_valid_answersheet", True) if isinstance(ocr_result, dict) else True
        invalid_reason = ocr_result.get("invalid_reason", "") if isinstance(ocr_result, dict) else ""
        raw_answers = ocr_result.get("answers", ocr_result) if isinstance(ocr_result, dict) else ocr_result
        if not isinstance(raw_answers, dict):
            raw_answers = {}
        student_answers = {str(k): v for k, v in raw_answers.items()}

        # 5. Context
        chapter_docs = await db.textbook_chapters.find({
            "standard": str(paper.get("standard")),
            "subject": paper.get("subject"),
            "chapter_title": {"$in": paper.get("chapters_used", [])}
        }).sort("passage_index", 1).to_list(None)

        # Group by chapter title
        chapter_map = {}
        for doc in chapter_docs:
            title = doc.get("chapter_title")
            content = doc.get("content", "")
            if title not in chapter_map:
                chapter_map[title] = []
            chapter_map[title].append(content)

        context_text = ""
        for title, contents in chapter_map.items():
            full_context = "\n".join(contents)
            context_text += f"\n=== {title} ===\n{full_context[:100000]}\n"
        
        if not context_text:
            context_text = "Evaluate using general academic knowledge."

        # If image was detected as invalid (e.g. placeholder file icon like 'JPG', blank, or non-exam file):
        if not is_valid_paper:
            print(f"[Evaluation] Invalid answersheet uploaded for eval {eval_oid}: {invalid_reason}")
            detailed_results = []
            q_number = 1
            for section in paper["sections"]:
                marks = section["marks_per_question"]
                for q in section["questions"]:
                    max_total += marks
                    detailed_results.append({
                        "q_no": q_number,
                        "question": q["question"],
                        "student_answer": "[Not Attempted - Invalid Image Uploaded]",
                        "max_marks": marks,
                        "score": 0.0,
                        "pct": 0.0,
                        "status": "not_attempted",
                        "feedback": invalid_reason or "The uploaded image is not a valid handwritten exam answersheet. It appears to be an icon, placeholder, or non-exam file.",
                        "ideal_answer": "No handwritten answersheet was detected.",
                        "grading_error": False,
                        "ai_tutor_context": None
                    })
                    q_number += 1

            total_score = 0.0
            score_pct = 0.0
            grade = "D"
            evaluation_status = "COMPLETED"

            section_performance = calculate_section_performance(
                paper.get("sections", []), detailed_results
            )
            topic_analysis = {
                "chapter_performance": {},
                "strong_areas": [],
                "weak_areas": paper.get("chapters_used", []),
                "skill_gap": "No valid exam paper was uploaded for evaluation.",
                "recommendations": ["Please upload a clear photo or scan of your handwritten answersheet."],
                "weakness_quiz": []
            }
        else:
            # 6. Evaluation — build task list for concurrent execution
            grading_tasks = []
            task_meta = []  # (q_number, question_text, student_ans, marks)
            q_number = 1

            for section in paper["sections"]:
                marks = section["marks_per_question"]
                for q in section["questions"]:
                    student_ans = student_answers.get(str(q_number), "[Not Attempted]")
                    grading_tasks.append(
                        evaluate_answer(q["question"], student_ans, marks, context_text, student_id, model)
                    )
                    task_meta.append((q_number, q["question"], student_ans, marks))
                    q_number += 1

            # Fire all grading calls concurrently
            print(f"[Evaluation] Grading {len(grading_tasks)} questions concurrently...")
            eval_results = await asyncio.gather(*grading_tasks)

            detailed_results = []
            for (q_no, question_text, student_ans, marks), eval_result in zip(task_meta, eval_results):
                score = float(str(eval_result.get("score", "0")).split("/")[0])
                total_score += score
                max_total += marks

                detailed_results.append({
                    "q_no": q_no,
                    "question": question_text,
                    "student_answer": student_ans,
                    "max_marks": marks,
                    "score": score,
                    "pct": round((score / marks * 100) if marks > 0 else 0.0, 1),
                    "status": _question_status(score, marks, student_ans),
                    "feedback": eval_result.get("feedback"),
                    "ideal_answer": eval_result.get("ideal_answer"),
                    "grading_error": eval_result.get("grading_error", False),
                    "ai_tutor_context": (
                        f"Question: {question_text}\n"
                        f"My Answer: {student_ans}\n"
                        f"Feedback received: {eval_result.get('feedback')}\n"
                        f"Ideal Answer: {eval_result.get('ideal_answer')}\n\n"
                        "Can you help me understand why my answer was wrong and explain the correct concept?"
                    ) if _question_status(score, marks, student_ans) in ["wrong", "partial"] else None
                })

            evaluation_status = "COMPLETED"
            score_pct = round((total_score / max_total * 100) if max_total > 0 else 0.0, 1)
            grade = _grade_from_pct(score_pct)

            # 7. Section performance (pure math, no AI)
            section_performance = calculate_section_performance(
                paper.get("sections", []), detailed_results
            )

            # 8. Topic & Chapter analysis (one GPT-4o-mini call)
            chapters_used = paper.get("chapters_used", [])
            subject = paper.get("subject", "")
            topic_analysis = await analyze_topic_strengths(
                detailed_results, chapters_used, subject, student_id
            )

        # Save full enriched evaluation record
        await db.evaluations.update_one(
            {"_id": ObjectId(eval_oid)},
            {
                "$set": {
                    "status": evaluation_status,
                    "subject": subject,
                    "standard": paper.get("standard", ""),
                    "chapters_used": chapters_used,
                    "total_score": total_score,
                    "max_total": max_total,
                    "score_pct": score_pct,
                    "grade": grade,
                    "detailed_results": detailed_results,
                    "section_performance": section_performance,
                    "topic_analysis": topic_analysis,
                    "completed_at": datetime.datetime.utcnow().isoformat()
                }
            }
        )

    except Exception as e:
        error_message = str(e)
        print(f"Background Evaluation Failed: {e}")
        
        await db.evaluations.update_one(
            {"_id": ObjectId(eval_oid)},
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
                if not is_valid_paper:
                    notif_title = "Evaluation: Invalid Answersheet"
                    notif_msg = f"The uploaded file was not a valid handwritten exam paper. Score: 0/{max_total}. Please upload a clear photo of your handwritten answers."
                else:
                    notif_title = "Evaluation Completed"
                    notif_msg = f"Your evaluation is complete. Score: {total_score}/{max_total}."

                await create_notification(
                    db=db,
                    user_id=student_id,
                    title=notif_title,
                    message=notif_msg,
                    notification_type="evaluation_completed",
                    # extra_data={"evaluation_id": eval_oid}
                    extra_data={"evaluation_id": eval_oid} 
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
    model: str = Form("gpt-4o-mini"),
    current_user: dict = Depends(get_current_user)
):
    # 🚨 Check & Use Quota (1 evaluation)
    await check_and_use_quota(student_id, "exam", cost=1)

    saved_file_paths = []
    
    try:
        # 1. Save files locally (must be done in main thread to await UploadFile)
        os.makedirs("temp", exist_ok=True)
        for file in files:
            ext = file.filename.split(".")[-1]
            path = f"temp/{uuid.uuid4()}.{ext}"
            with open(path, "wb") as f:
                f.write(await file.read())
            saved_file_paths.append(path)

        try:
            s_oid = ObjectId(student_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid student ID format (must be 24-char hex)")

        # 2. Create Initial DB Record
        initial_evaluation_data = {
            "paper_id": paper_id,
            "student_id": s_oid,
            "status": "PROCESSING",
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        result = await db.evaluations.insert_one(initial_evaluation_data)
        eval_oid = str(result.inserted_id)

        # 3. Add Background Task
        background_tasks.add_task(
            process_evaluation_background,
            eval_oid,
            paper_id,
            str(s_oid), # Convert ObjectId to str for safety in background task args
            saved_file_paths,
            model
        )

        return JSONResponse(
            status_code=200,
            content={
                "status": True,
                "message": "Evaluation started in background.",
                "data": {
                    "evaluation_id": eval_oid,
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

    try:
        s_oid = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format (must be 24-char hex)")

    notifications = await db.notifications.find(
        {"student_id": str(s_oid), "is_read": False}
    ).sort("created_at", -1).to_list(100)

    return {"status": True, "data": clean_mongo(notifications)}

@router.post("/notifications/read/{notification_id}")
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("student_id")

    # Build query
    try:
        query = {
            "_id": ObjectId(notification_id)
        }
    except:
        raise HTTPException(status_code=400, detail="Invalid notification_id format")

    # Ensure notification belongs to the current user
    if user_id:
        try:
            query["student_id"] = ObjectId(user_id)
        except:
            raise HTTPException(
                status_code=400,
                detail="Invalid student_id format in token"
            )

    result = await db.notifications.update_one(
        query,
        {"$set": {"is_read": True}}
    )

    if result.matched_count == 0:
        return JSONResponse(
            status_code=404,
            content={
                "status": False,
                "message": "Notification not found"
            }
        )

    return {
        "status": True,
        "message": "Notification marked as read"
    }
@router.get("/exam-history/{student_id}")
async def get_exam_history(
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch paginated exam evaluations for a specific student.
    Returns full enriched details for each exam.
    """

    # 🔐 Ownership check
    user_student_id = current_user.get("student_id")

    if user_student_id and user_student_id != student_id:
        raise HTTPException(status_code=403, detail="Unauthorized access to exam history")
    
    # 🆔 Validate ObjectId
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(
            status_code=400,
            detail="Invalid student_id format (must be 24-char hex)"
        )

    # 📌 Pagination math
    skip = (page - 1) * limit

    # 📊 Fetch data
    cursor = (
        db.evaluations
        .find({"student_id": s_oid})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )

    evaluations = await cursor.to_list(length=limit)
    
    # 🧹 Clean and Enrich each evaluation record
    enriched_data = []
    for ev in evaluations:
        cleaned = clean_mongo(ev)
        enriched = await enrich_evaluation_data(cleaned)
        enriched_data.append(enriched)

    # 📈 Total count (for has_more)
    total_count = await db.evaluations.count_documents({"student_id": s_oid})

    return {
        "status": True,
        "message": "Exam history retrieved successfully.",
        "page": page,
        "limit": limit,
        "total": total_count,
        "has_more": skip + limit < total_count,
        "data": enriched_data
    }

async def enrich_evaluation_data(data: dict):
    """
    Shared enrichment logic for evaluation records (Detail & History).
    Ensures legacy records have subject, scores, and per-question status/prompts.
    """
    # 1. Enrich from generated_papers if subject or section_performance is missing
    if not data.get("subject") or not data.get("section_performance"):
        paper_id = data.get("paper_id")
        if paper_id:
            paper_doc = await db.generated_papers.find_one({"paper.paper_id": paper_id})
            if paper_doc:
                paper = paper_doc.get("paper", {})
                if not data.get("subject"):
                    data["subject"] = paper.get("subject", "")
                    data["standard"] = paper.get("standard", "")
                    data["chapters_used"] = paper.get("chapters_used", [])
                
                if not data.get("section_performance") and data.get("detailed_results"):
                    data["section_performance"] = calculate_section_performance(
                        paper.get("sections", []), data["detailed_results"]
                    )

    # 2. Add score_pct and grade if missing
    if not data.get("score_pct") and data.get("max_total"):
        total = data.get("total_score", 0)
        max_t = data.get("max_total", 0)
        data["score_pct"] = round((total / max_t * 100) if max_t > 0 else 0.0, 1)
        data["grade"] = _grade_from_pct(data["score_pct"])

    # 3. Enrich per-question results
    for r in data.get("detailed_results", []):
        score = r.get("score", 0)
        max_m = r.get("max_marks", 0)
        ans = r.get("student_answer", "")
        
        # Add status and pct if missing
        if "status" not in r:
            r["status"] = _question_status(score, max_m, ans)
        if "pct" not in r and max_m:
            r["pct"] = round((score / max_m * 100), 1)
            
        # Add ai_tutor_context if missing for wrong/partial answers
        if not r.get("ai_tutor_context") and r["status"] in ["wrong", "partial"]:
            r["ai_tutor_context"] = (
                f"Question: {r.get('question')}\n"
                f"My Answer: {ans}\n"
                f"Feedback received: {r.get('feedback')}\n"
                f"Ideal Answer: {r.get('ideal_answer')}\n\n"
                "Can you help me understand why my answer was wrong and explain the correct concept?"
            )
            
    return data

@router.get("/evaluation-detail/{evaluation_id}")
async def get_evaluation_detail(evaluation_id: str, current_user: dict = Depends(get_current_user)):
    """
    Fetch full details of a specific exam evaluation.
    Uses shared enrichment logic to ensure complete data.
    """
    try:
        e_oid = ObjectId(evaluation_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid evaluation ID format")

    evaluation = await db.evaluations.find_one({"_id": e_oid})

    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # 🔐 Ownership check
    user_student_id = current_user.get("student_id")
    if user_student_id and user_student_id != str(evaluation.get("student_id")):
        raise HTTPException(status_code=403, detail="Unauthorized access to evaluation details")

    data = clean_mongo(evaluation)
    
    # 🚀 Apply enrichment
    enriched_data = await enrich_evaluation_data(data)

    return {
        "status": True,
        "message": "Evaluation details retrieved successfully.",
        "data": enriched_data
    }


@router.get("/evaluation-insights/{student_id}")
async def get_evaluation_insights(student_id: str, current_user: dict = Depends(get_current_user)):
    """
    Aggregated performance insights across ALL completed evaluations for a student.
    Powers Flutter dashboard: score trend, subject radar, chapter trends, badges.
    """
    # 🔐 Ownership check
    user_student_id = current_user.get("student_id")
    if user_student_id and user_student_id != student_id:
        raise HTTPException(status_code=403, detail="Unauthorized access to insights")

    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    # Fetch all COMPLETED evaluations, oldest first (for trend)
    evaluations = await db.evaluations.find(
        {"student_id": s_oid, "status": "COMPLETED"}
    ).sort("created_at", 1).to_list(None)

    if not evaluations:
        return {
            "status": True,
            "message": "No completed evaluations found.",
            "data": {
                "total_exams": 0,
                "score_trend": [],
                "subject_performance": {},
                "section_avg": {},
                "chapter_trends": {},
                "persistent_weak_areas": [],
                "persistent_strong_areas": [],
                "weakness_quizzes": [],
                "question_accuracy": {"correct_pct": 0, "partial_pct": 0, "wrong_pct": 0, "not_attempted_pct": 0},
                "performance_badge": "No Data",
                "average_score_pct": 0,
                "best_score_pct": 0,
                "latest_score_pct": 0,
                "improvement_pct": 0
            }
        }

    # ── 1. Score Trend ──────────────────────────────────────────────
    score_trend = []
    all_score_pcts = []

    for ev in evaluations:
        total = ev.get("total_score", 0)
        max_t = ev.get("max_total", 0)
        pct = round((total / max_t * 100) if max_t > 0 else 0.0, 1)
        ev["_score_pct"] = pct  # cache for later use
        all_score_pcts.append(pct)
        score_trend.append({
            "date": ev.get("created_at", ""),
            "subject": ev.get("subject", "Unknown"),
            "standard": ev.get("standard", ""),
            "score_pct": pct,
            "grade": ev.get("grade") or _grade_from_pct(pct),
            "evaluation_id": str(ev["_id"])
        })

    # ── 2. Subject Performance ──────────────────────────────────────
    subject_map = {}
    for ev in evaluations:
        subj = ev.get("subject", "Unknown")
        pct = ev["_score_pct"]
        if subj not in subject_map:
            subject_map[subj] = {"scores": [], "best": 0.0}
        subject_map[subj]["scores"].append(pct)
        subject_map[subj]["best"] = max(subject_map[subj]["best"], pct)

    subject_performance = {
        subj: {
            "avg_pct": round(sum(d["scores"]) / len(d["scores"]), 1),
            "best_pct": round(d["best"], 1),
            "attempts": len(d["scores"])
        }
        for subj, d in subject_map.items()
    }

    # ── 3. Section Averages ─────────────────────────────────────────
    section_sums = {}   # letter -> {total_score, total_max}
    for ev in evaluations:
        for letter, sp in (ev.get("section_performance") or {}).items():
            if letter not in section_sums:
                section_sums[letter] = {"score": 0.0, "max": 0.0}
            section_sums[letter]["score"] += sp.get("score", 0)
            section_sums[letter]["max"]   += sp.get("max", 0)

    section_avg = {
        letter: round((v["score"] / v["max"] * 100) if v["max"] > 0 else 0.0, 1)
        for letter, v in section_sums.items()
    }

    # ── 4. Chapter Trends & Persistent Areas ───────────────────────
    chapter_tracker = {}   # chapter_name -> {appearances, scores, labels, weak_count, strong_count}
    
    # Fuzzy Match Helper for Topics
    def get_fuzzy_topic_group(topic, topic_groups, threshold=0.6):
        """Finds or creates a fuzzy group for a topic name."""
        topic_clean = topic.lower().strip()
        for group_name in topic_groups.keys():
            if difflib.SequenceMatcher(None, topic_clean, group_name.lower()).ratio() > threshold:
                return group_name
        return topic # New group
    
    weak_topic_counts = {}   # Resolved Topic -> Frequency
    strong_topic_counts = {} # Resolved Topic -> Frequency
    
    # Recent items for new students (Fall-back)
    recent_weak = []
    recent_strong = []

    for ev in evaluations:
        ta = ev.get("topic_analysis") or {}

        # Chapter-level tracking
        for ch_name, ch_data in (ta.get("chapter_performance") or {}).items():
            if ch_name not in chapter_tracker:
                chapter_tracker[ch_name] = {"appearances": 0, "scores": [], "strength_labels": []}
            chapter_tracker[ch_name]["appearances"] += 1
            chapter_tracker[ch_name]["scores"].append(ch_data.get("pct", 0))
            chapter_tracker[ch_name]["strength_labels"].append(ch_data.get("strength", "average"))

        # Topic-level tracking with Fuzzy Matching
        curr_weak = ta.get("weak_areas") or []
        curr_strong = ta.get("strong_areas") or []
        
        # Track recent items for students with 1-2 exams
        if ev == evaluations[-1]:
            recent_weak = curr_weak
            recent_strong = curr_strong

        for topic in curr_weak:
            resolved = get_fuzzy_topic_group(topic, weak_topic_counts)
            weak_topic_counts[resolved] = weak_topic_counts.get(resolved, 0) + 1
            
        for topic in curr_strong:
            resolved = get_fuzzy_topic_group(topic, strong_topic_counts)
            strong_topic_counts[resolved] = strong_topic_counts.get(resolved, 0) + 1

    # Get the latest generated quiz to provide to the frontend
    latest_weakness_quiz = []
    if evaluations:
        latest_eval = evaluations[-1]
        ta = latest_eval.get("topic_analysis") or {}
        latest_weakness_quiz = ta.get("weakness_quiz", [])

    # Chapter Trends
    chapter_trends = {
        ch: {
            "appearances": d["appearances"],
            "avg_pct": round(sum(d["scores"]) / len(d["scores"]), 1) if d["scores"] else 0.0,
            "trend": (
                "improving" if len(d["scores"]) >= 2 and d["scores"][-1] > d["scores"][0]
                else "declining" if len(d["scores"]) >= 2 and d["scores"][-1] < d["scores"][0]
                else "stable"
            ),
            "last_strength": d["strength_labels"][-1] if d["strength_labels"] else "average"
        }
        for ch, d in chapter_tracker.items()
    }

    # PERSISTENCE LOGIC
    # If student has < 3 exams, we show "Recent Areas" to avoid empty lists.
    # If student has >= 3 exams, we only show "Persistent" (Repeated) areas.
    
    if len(evaluations) < 3:
        # Show all topics from most recent eval, plus any that actually repeated
        persistent_weak_areas = list(set(recent_weak + [t for t, c in weak_topic_counts.items() if c >= 2]))
        persistent_strong_areas = list(set(recent_strong + [t for t, c in strong_topic_counts.items() if c >= 2]))
    else:
        # Strict Persistence (Repeated topics)
        persistent_weak_areas = [t for t, c in weak_topic_counts.items() if c >= 2]
        persistent_strong_areas = [t for t, c in strong_topic_counts.items() if c >= 2]
        
    # CHAPTER PERSISTENCE (Bonus Layer)
    # If a chapter appears as "weak" in last 2 exams, add it to weak list if not there
    for ch, d in chapter_tracker.items():
        if d["appearances"] >= 2:
            last_two = d["strength_labels"][-2:]
            if all(s == "weak" for s in last_two):
                ch_label = f"Chapter: {ch}"
                if ch_label not in persistent_weak_areas:
                    persistent_weak_areas.append(ch_label)
            elif all(s == "strong" for s in last_two):
                ch_label = f"Chapter: {ch}"
                if ch_label not in persistent_strong_areas:
                    persistent_strong_areas.append(ch_label)

    # ── 5. Question Accuracy Breakdown ─────────────────────────────
    total_q = correct_q = partial_q = wrong_q = not_attempted_q = 0
    for ev in evaluations:
        for r in (ev.get("detailed_results") or []):
            total_q += 1
            st = r.get("status") or _question_status(
                r.get("score", 0), r.get("max_marks", 0), r.get("student_answer", "")
            )
            if st == "correct":       correct_q += 1
            elif st == "partial":     partial_q += 1
            elif st == "wrong":       wrong_q += 1
            else:                     not_attempted_q += 1

    def _pct(n): return round(n / total_q * 100, 1) if total_q > 0 else 0.0
    question_accuracy = {
        "correct_pct":       _pct(correct_q),
        "partial_pct":       _pct(partial_q),
        "wrong_pct":         _pct(wrong_q),
        "not_attempted_pct": _pct(not_attempted_q)
    }

    # ── 6. Overall Stats & Badge ────────────────────────────────────
    avg_score_pct    = round(sum(all_score_pcts) / len(all_score_pcts), 1)
    best_score_pct   = round(max(all_score_pcts), 1)
    latest_score_pct = all_score_pcts[-1]
    first_score_pct  = all_score_pcts[0]
    improvement_pct  = round(latest_score_pct - first_score_pct, 1)

    # Badge logic
    if len(all_score_pcts) < 2:
        badge = "New"
    elif improvement_pct >= 10:
        badge = "Improving"
    elif abs(improvement_pct) < 10:
        badge = "Consistent"
    else:
        badge = "Needs Attention"

    return {
        "status": True,
        "message": "Evaluation insights retrieved successfully.",
        "data": {
            "total_exams": len(evaluations),
            "average_score_pct": avg_score_pct,
            "best_score_pct": best_score_pct,
            "latest_score_pct": latest_score_pct,
            "improvement_pct": improvement_pct,
            "performance_badge": badge,
            "score_trend": score_trend,
            "subject_performance": subject_performance,
            "section_avg": section_avg,
            "chapter_trends": chapter_trends,
            "persistent_weak_areas": persistent_weak_areas,
            "persistent_strong_areas": persistent_strong_areas,
            "weakness_quizzes": latest_weakness_quiz,
            "question_accuracy": question_accuracy
        }
    }
