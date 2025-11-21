from fastapi import APIRouter
from models.user_models import UserCreate, Student, UserTypeRequest
from models.answer_models import AnswerRequest
from core.database import db
from datetime import datetime, timezone
from fastapi import Query, HTTPException
from typing import Dict, List
from models.career_models import CareerAnalyzer
from bson import ObjectId
from fastapi import APIRouter, Form, HTTPException, Depends, File, UploadFile
import re
router = APIRouter(tags=["User"])

# --------------------- Student Registration -------------------------
async def generate_student_id():
    count = await db.students.count_documents({})
    return f"STU{str(count+1).zfill(4)}"

@router.post("/register-student")
async def register_student(
    data: Student,
    parent_mobile: str = Query(..., description="Parent mobile number")
):
    student_id = await generate_student_id()

    student_doc = {
        "student_id": student_id,
        "student_name": data.student_name,
        "dob": data.dob,
        "student_class": data.student_class,
        "age": data.age,
        "address": data.address,
        "guardian_name": data.guardian_name,
        "created_at": datetime.now(timezone.utc),
        "is_user": False
    }

    await db.students.insert_one(student_doc)

    await db.usertable.update_one(
        {"mobile_number": parent_mobile},
        {
            "$setOnInsert": {
                "usertype": "parent",
                "created_at": datetime.now(timezone.utc)
            },
            "$addToSet": {"student_ids": student_id}
        },
        upsert=True
    )

    return {
        "status_code": 200,
        "message": "Student registered successfully",
        "student_id": student_id
    }

def clean_mongo_doc(doc):
    if not doc:
        return doc
    doc["_id"] = str(doc["_id"])
    return doc

# --------------------- Fetch Parent Details -------------------------
@router.get("/parent")
async def get_parent_details(mobile_number: str = Query(..., description="The mobile number of the parent")):
    user_record = await db.usertable.find_one({"mobile_number": mobile_number})
    if not user_record:
        return {"status_code": 404, "message": "Parent not found"}

    student_ids = user_record.get("student_ids", [])
    students = []
    if student_ids:
        cursor = db.students.find({"student_id": {"$in": student_ids}})
        students = [clean_mongo_doc(doc) for doc in await cursor.to_list(length=None)]

    return {"status_code": 200, "parent_number": mobile_number, "students": students}
@router.post("/set-usertype")
async def set_usertype(data: UserTypeRequest):
    record = await db.otps.find_one({"mobile_number": data.mobile_number})
    if not record:
        return {"status_code": 400, "message": "User not found"}

    await db.otps.update_one(
        {"mobile_number": data.mobile_number},
        {"$set": {"usertype": data.usertype}}
    )
    await db.usertable.update_one(
        {"mobile_number": data.mobile_number},
        {"$set": {"usertype": data.usertype}}
    )

    return {
        "status_code": 200,
        "message": f"Usertype set to {data.usertype}"
    }
# --------------------- Questions by Age -------------------------
@router.get("/student_questions")
async def get_questions_by_age(age: int = Query(...)):
    # Find questions where age_min <= age <= age_max
    query = {
        "$and": [
            {"age_min": {"$lte": age}},
            {"age_max": {"$gte": age}}
        ]
    }

    cursor = db.questions.find(query)
    questions = [clean_mongo_doc(doc) for doc in await cursor.to_list(length=None)]

    grouped: Dict[str, List[dict]] = {}

    for q in questions:
        cat = q.get("category", "uncategorized")

        # Detect type of question
        is_image_question = "image_options" in q and q["image_options"]

        # Build question payload
        question_data = {
    "id": q["_id"],
    "text": q.get("text"),
}

        if q.get("type") == "image":
           question_data["type"] = "image"
           question_data["options"] = q.get("image_options", [])  # list of image URLs
           question_data["correct_index"] = q.get("correct_index")

        elif q.get("type") == "rating":
    # ⭐ Text-based Rating (no options)
           question_data["type"] = "rating"
    # Only text, min_age, max_age (if available)
           question_data["age_min"] = q.get("age_min")
           question_data["age_max"] = q.get("age_max")

        else:
    # 📝 Text-based MCQ
           question_data["type"] = "text"
           question_data["options"] = q.get("options", [])
           question_data["correct_answer"] = q.get("correct_answer")

        # Group by category
        grouped.setdefault(cat, []).append(question_data)

    return {
        "status_code": 200,
        "age": age,
        "categories": grouped
    }

# --------------------- Save Answer -------------------------
 

from datetime import datetime, timezone
from bson import ObjectId
from fastapi import HTTPException

@router.post("/answers")
async def save_answers(payload: AnswerRequest):

    answers_list = []
    total_marks = 0
    rating_values = []

    # Process each question + answer
    for qid, ans in zip(payload.question_ids, payload.answers):
        question = await db.questions.find_one({"_id": ObjectId(qid)})
        if not question:
            continue

        q_type = question.get("type")
        correct_index = question.get("correct_index")

        if q_type == "rating":
            rating_values.append(ans)
            mark = 0
        else:
            mark = 1 if ans == correct_index else 0
            total_marks += mark

        answers_list.append({
            "question_id": qid,
            "answer_value": ans,
            "correct_index": correct_index,
            "type": q_type,
            "mark": mark
        })

    # Compute rating avg + add to total marks
    rating_avg = sum(rating_values) / len(rating_values) if rating_values else 0
    total_marks += rating_avg

    # ---------------------------------------
    # AUTO ATTEMPT & STATUS LOGIC
    # ---------------------------------------
    existing_doc = await db.answers.find_one({"student_id": payload.student_id})

    if not existing_doc:
        # 🟢 First ever record for student
        attempt = 1
        new_doc = {
            "student_id": payload.student_id,
            "attempts": [
                {
                    "attempt": attempt,
                    "status": "in-progress",
                    "timestamp_utc": datetime.now(timezone.utc),
                    "categories": [{
                        "category": payload.category,
                        "total_marks": total_marks,
                        "answers": answers_list
                    }]
                }
            ]
        }
        await db.answers.insert_one(new_doc)
        print(f"✅ Created first attempt (1) for {payload.student_id}")

    else:
        # 🟡 Student already exists
        attempts = existing_doc.get("attempts", [])
        if not attempts:
            attempt = 1
        else:
            last_attempt = attempts[-1]
            attempt = last_attempt["attempt"]

            # If last attempt is completed → new attempt
            if last_attempt["status"] == "completed":
                attempt += 1
                await db.answers.update_one(
                    {"student_id": payload.student_id},
                    {"$push": {
                        "attempts": {
                            "attempt": attempt,
                            "status": "in-progress",
                            "timestamp_utc": datetime.now(timezone.utc),
                            "categories": []
                        }
                    }}
                )
                print(f"🟢 Created new attempt {attempt} for {payload.student_id}")

        # Fetch latest document again after potential new attempt creation
        student_doc = await db.answers.find_one({"student_id": payload.student_id})
        active_attempt = next(
            (a for a in student_doc["attempts"] if a["attempt"] == attempt),
            None
        )

        if not active_attempt:
            raise HTTPException(status_code=500, detail="Attempt not found after update.")

        # Remove existing category if re-submitted
        updated_categories = [
            c for c in active_attempt.get("categories", [])
            if c["category"] != payload.category
        ]
        updated_categories.append({
            "category": payload.category,
            "total_marks": total_marks,
            "answers": answers_list
        })

        # Update DB
        await db.answers.update_one(
            {"student_id": payload.student_id, "attempts.attempt": attempt},
            {"$set": {"attempts.$.categories": updated_categories}}
        )

        # ---------------------------------------
        # AUTO MARK ATTEMPT AS COMPLETED
        # ---------------------------------------
        total_category_count = len(updated_categories)
        if total_category_count >= 8:  # if all 8 intelligence types answered
            await db.answers.update_one(
                {"student_id": payload.student_id, "attempts.attempt": attempt},
                {"$set": {"attempts.$.status": "completed"}}
            )
            print(f"🏁 Attempt {attempt} marked as COMPLETED for {payload.student_id}")

    # Debug log
    updated_doc = await db.answers.find_one({"student_id": payload.student_id})
    print("🔍 Updated document:\n", updated_doc)

    return {
        "status_code": 200,
        "message": f"Answers saved for category '{payload.category}' (Attempt {attempt})",
        "rating_average": rating_avg,
        "total_marks": total_marks
    }



@router.get("/get_students")
async def get_students():
    cursor = db.students.find({}, {"_id": 0})  # exclude MongoDB _id
    students = await cursor.to_list(length=None)
    return {
        "status_code": 200,
        "students": students
    }


# from bson import ObjectId
# @router.post("/answers")
# async def save_answers(payload: AnswerRequest):

#     answers_list = []
#     total_marks = 0
#     rating_values = []  # collect rating answers

#     # Loop through each question + answer
#     for qid, ans in zip(payload.question_ids, payload.answers):

#         # Fetch question
#         question = await db.questions.find_one({"_id": ObjectId(qid)})
#         if not question:
#             continue

#         q_type = question.get("type")
#         correct_index = question.get("correct_index")

#         # ============================
#         # 1) HANDLE RATING QUESTIONS
#         # ============================
#         if q_type == "rating":
#             rating_values.append(ans)    # store rating
#             mark = 0                     # rating gives no direct mark
#         else:
#             # ==============================
#             # 2) HANDLE MCQ QUESTIONS (text/image)
#             # ==============================
#             mark = 1 if ans == correct_index else 0
#             total_marks += mark

#         # Append answer details
#         answers_list.append({
#             "question_id": qid,
#             "answer_value": ans,
#             "correct_index": correct_index,
#             "type": q_type,
#             "mark": mark
#         })

#     # ==============================
#     # 3) CALCULATE RATING AVERAGE
#     # ==============================
#     if rating_values:
#         rating_avg = sum(rating_values) / len(rating_values)
#         total_marks += rating_avg
#     else:
#         rating_avg = 0

#     # Default attempt = 0
#     attempt = getattr(payload, "attempt", 0)

#     # Final document
#     document = {
#         "student_id": payload.student_id,
#         "category": payload.category,
#         "attempt": attempt,
#         "answers": answers_list,
#         "rating_average": rating_avg,
#         "total_marks": total_marks,
#         "timestamp": datetime.now(timezone.utc)
#     }

#     result = await db.answers.insert_one(document)

#     return {
#         "status_code": 200,
#         "message": "All answers saved",
#         "answer_sheet_id": str(result.inserted_id),
#         "rating_average": rating_avg,
#         "total_marks": total_marks
#     }

# ✅ Get all Users (Parents table)
@router.get("/get_users")
async def get_users():
    cursor = db.usertable.find({}, {"_id": 0})
    users = await cursor.to_list(length=None)
    return {
        "status_code": 200,
        "users": users
    }

# ✅ Get all Login Attempts (OTP table)
@router.get("/get_logins")
async def get_logins():
    cursor = db.otps.find({}, {"_id": 0})
    logins = await cursor.to_list(length=None)
    return {
        "status_code": 200,
        "logins": logins
    }

# --------------------- Career Analyzer Logic -------------------------
from fastapi import HTTPException
from datetime import datetime, timezone

career_map = {
    "musical": "Musician, Composer, Singer, Sound Engineer",
    "logical-mathematical": "Scientist, Engineer, Mathematician, Data Analyst",
    "verbal-linguistic": "Writer, Journalist, Teacher, Lawyer",
    "bodily-kinesthetic": "Athlete, Dancer, Physical Therapist, Surgeon",
    "visual-spatial": "Architect, Designer, Artist, Pilot",
    "interpersonal": "Teacher, Counselor, Manager, Salesperson",
    "intrapersonal": "Psychologist, Philosopher, Writer",
    "naturalist": "Biologist, Environmentalist, Farmer, Veterinarian"
}


import matplotlib.pyplot as plt
import base64
from io import BytesIO
from datetime import datetime, timezone
import math
from fastapi import HTTPException
def normalize_percentages(scores: dict) -> dict:
    total = sum(scores.values())

    # If total is 0 → return all zeros
    if total == 0:
        return {k: 0 for k in scores}

    # 1️⃣ Exact percentages
    exact = {k: (v / total) * 100 for k, v in scores.items()}

    # 2️⃣ Floor values
    floor_pct = {k: math.floor(p) for k, p in exact.items()}

    # 3️⃣ Remaining percentage points to distribute
    remaining = 100 - sum(floor_pct.values())

    # 4️⃣ Sort categories by fractional remainder descending
    remainders = [(k, exact[k] - floor_pct[k], scores[k]) for k in scores]
    remainders.sort(key=lambda x: (-x[1], -x[2]))

    # 5️⃣ Distribute remaining points
    result = floor_pct.copy()
    for i in range(remaining):
        key = remainders[i][0]
        result[key] += 1

    return result


@router.post("/analyze-career/{student_id}")
async def analyze_career(student_id: str):
    """Automatically analyze the latest *completed* attempt for a student"""

    # 1️⃣ Fetch student answers document
    student_doc = await db.answers.find_one({"student_id": student_id})
    if not student_doc:
        raise HTTPException(status_code=404, detail="No answers found for this student")

    attempts = student_doc.get("attempts", [])
    if not attempts:
        raise HTTPException(status_code=404, detail="No attempts found for this student")

    # 2️⃣ Find the latest completed attempt
    completed_attempts = [a for a in attempts if a.get("status") == "completed"]
    if not completed_attempts:
        raise HTTPException(
            status_code=400,
            detail="No completed attempt found. Please finish all categories first."
        )

    latest_attempt = max(completed_attempts, key=lambda a: a["attempt"])
    attempt_num = latest_attempt["attempt"]

    # 3️⃣ Extract categories & scores
    categories = latest_attempt.get("categories", [])
    if not categories:
        raise HTTPException(status_code=400, detail="No category data found in this attempt")

    scores = {cat["category"]: cat.get("total_marks", 0) for cat in categories}
    if not scores:
        raise HTTPException(status_code=400, detail="No valid scores found")

    # ➕ 3.1 Use the **correct** normalized percentages
    percentages = normalize_percentages(scores)

    # 4️⃣ Determine top 3 and best category
    top_3 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cat = top_3[0][0]
    recommended_career = career_map.get(top_cat.lower(), "No career mapped")

    # 5️⃣ Personality insights and career suggestions
    insights = [
        f"{cat}: Strong inclination towards {cat.lower()} intelligence."
        for cat, _ in top_3
    ]
    career_suggestions = [
        f"{cat} ➔ {career_map.get(cat.strip().lower(), 'Unknown Career')}"
        for cat, _ in top_3
    ]
    
    # recommended_career_list = (
    # recommended_career if isinstance(recommended_career, list)
    # else [career.strip() for career in recommended_career.split(",")])

    # 6️⃣ Save/update result in DB
    await db.career_analyzer.update_one(
        {"student_id": student_id, "attempt": attempt_num},
        {
            "$set": {
                "scores": scores,
                "overall_score": sum(scores.values()),
                "percentages": percentages,   # 📌 updated logic
                "top_category": top_cat,
                "recommended_career": recommended_career,
                "timestamp": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    # 7️⃣ API Response
    return {
        "status_code": 200,
        "student_id": student_id,
        "analyzed_attempt": attempt_num,
        "scores": scores,
        "overall_score": sum(scores.values()),
        "percentages": percentages,
        "top_category": top_cat,
        "recommended_career": recommended_career,
        "personality_insights": insights,
        "career_suggestions": career_suggestions
    }
from bson import json_util
import json


@router.get("/career-analysis/{student_id}/{attempt}")
async def get_career_analysis(student_id: str, attempt: int):
    """
    Fetch career analysis for a specific student and attempt number.
    """

    record = await db.career_analyzer.find_one(
        {"student_id": student_id, "attempt": attempt},
        {"_id": 0}   # hide MongoDB ObjectId
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No career analysis found for student {student_id} in attempt {attempt}"
        )

    return {
        "status_code": 200,
        "student_id": student_id,
        "attempt": attempt,
        "career_analysis": record
    }

@router.get("/career-result/{student_id}")
async def get_career_result(student_id: str):
    records = await db.career_analyzer.find({"student_id": student_id}).to_list(None)
    if not records:
        raise HTTPException(status_code=404, detail="No career result found")

    return json.loads(json_util.dumps({
        "student_id": student_id,
        "history": records
    }))

from fastapi import APIRouter, HTTPException
from bson import ObjectId


@router.get("/career-history/{student_id}")
async def get_career_history(student_id: str):

    # Get all career analysis attempts
    career_records = await db.career_analyzer.find({"student_id": student_id}).sort("timestamp", -1).to_list(None)
    if not career_records:
        raise HTTPException(status_code=200, detail="No career analysis found for this student")

    # Get student's answer document
    answers_doc = await db.answers.find_one({"student_id": student_id})
    if not answers_doc:
        raise HTTPException(status_code=200, detail="No answers found for this student")

    # Build detailed data per attempt
    full_attempts = []
    for attempt in answers_doc.get("attempts", []):
        categories_detailed = []

        for cat in attempt.get("categories", []):
            answers_detailed = []

            for ans in cat.get("answers", []):
                qid = ans["question_id"]

                # Fetch question details
                question = await db.questions.find_one(
                    {"_id": ObjectId(qid)},
                    {"text": 1, "type": 1, "options": 1, "image_options": 1,
                     "correct_index": 1, "correct_answer": 1}
                )

                # Extract data
                qtype = question.get("type")
                student_answer = ans.get("answer_value")
                correct_index = question.get("correct_index")

                # Convert both to string for robust matching ("2" vs 2)
                student_answer_s = str(student_answer).strip() if student_answer is not None else None
                correct_index_s = str(correct_index).strip() if correct_index is not None else None

                # Determine correctness
                if qtype == "rating":
                    is_correct = True
                else:
                    is_correct = (student_answer_s == correct_index_s)

                # Append detailed answer
                answers_detailed.append({
                    "question_id": qid,
                    "question_text": question.get("text"),
                    "options": question.get("options") or question.get("image_options"),
                    "student_answer": student_answer,
                    "type": qtype,
                    "correct_index": correct_index,
                    "correct_answer": question.get("correct_answer"),
                    "is_correct": is_correct
                })

            # Append category-level details
            categories_detailed.append({
                "category": cat["category"],
                "total_marks": cat["total_marks"],
                "answers": answers_detailed
            })

        # Append attempt-level details
        full_attempts.append({
            "attempt": attempt["attempt"],
            "timestamp_utc": attempt["timestamp_utc"],
            "status": attempt.get("status", "in-progress"),
            "categories": categories_detailed
        })

    # Merge attempts with career analysis results
    combined_history = []
    for record in career_records:
        attempt_no = record.get("attempt", 0)

        matching_attempt = next((a for a in full_attempts if a["attempt"] == attempt_no), None)

        combined_history.append({
            "attempt": attempt_no,
            "timestamp": record.get("timestamp"),
            "top_category": record.get("top_category"),
            "recommended_career": record.get("recommended_career"),
            "scores": record.get("scores"),
            "answers_detail": matching_attempt
        })

    return {
        "student_id": student_id,
        "total_attempts": len(combined_history),
        "career_history": combined_history
    }

# @router.post("/auto-generate-question")
# async def auto_generate_question(
#     student_id: str = Form(...),
#     subject: str = Form(...),
#     question_type: str = Form(...)
# ):
#     # 1️⃣ Fetch student data from DB
#     student = await db.students.find_one({"student_id": student_id})

#     if not student:
#         raise HTTPException(status_code=404, detail="Student not found")

#     # 2️⃣ Extract class automatically
#     class_level = student.get("student_class")
#     if not class_level:
#         raise HTTPException(status_code=400, detail="Student class not found in database")

#     # 3️⃣ Generate question automatically using student class
#     question = await generate_subject_question(subject, class_level, question_type)

#     return {
#         "status_code": 200,
#         "student_id": student_id,
#         "student_class": class_level,
#         "subject": subject,
#         "question_type": question_type,
#         "generated_question": question
#     }
# @router.post("/evaluate-answer")
# async def evaluate_student_answer(
#     student_id: str = Form(...),
#     question: str = Form(...),
#     answer: str = Form(...)
# ):
#     evaluation = await evaluate_answer(question, answer)

#     import re
#     score_match = re.search(r"Score:\s*(\d+)/10", evaluation)
#     score = int(score_match.group(1)) if score_match else 0

#     level = map_score_to_level(score)

#     record = {
#         "student_id": student_id,
#         "question": question,
#         "answer": answer,
#         "evaluation": evaluation,
#         "score": score,
#         "level": level,
#         "timestamp": datetime.now(timezone.utc)
#     }
#     await db.score_questions.insert_one(record)

#     return {
#         "status_code": 200,
#         "message": "Answer evaluated and saved successfully",
#         "score": score,
#         "level": level,
#         "evaluation": evaluation
#     }
