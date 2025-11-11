from fastapi import APIRouter
from models.user_models import UserCreate, Student, UserTypeRequest
from models.answer_models import AnswerRequest
from core.database import db
from datetime import datetime, timezone
from fastapi import Query, HTTPException
from typing import Dict, List
from models.career_models import Career_analyzer
from bson import ObjectId

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
@router.post("/answers")
async def save_answers(payload: AnswerRequest):

    answers_list = []
    total_marks = 0

    # Loop through each question + answer
    for qid, ans in zip(payload.question_ids, payload.answers):

        # Fetch question
        question = await db.questions.find_one({"_id": ObjectId(qid)})
        if not question:
            continue  # skip missing questions

        correct_index = question.get("correct_index")

        # Mark calculation
        mark = 1 if ans == correct_index else 0
        total_marks += mark

        # Add to answers list
        answers_list.append({
            "question_id": qid,
            "answer_value": ans,
            "correct_index": correct_index,
            "mark": mark
        })

    # Default attempt = 0
    attempt = getattr(payload, "attempt", 0)

    # Final combined document
    document = {
        "student_id": payload.student_id,
        "category": payload.category,
        "attempt": attempt,
        "answers": answers_list,
        "total_marks": total_marks,
        "timestamp": datetime.now(timezone.utc)
    }

    # Insert into Mongo
    result = await db.answers.insert_one(document)

    return {
        "status_code": 200,
        "message": "All answers saved",
        "answer_sheet_id": str(result.inserted_id),
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
from bson import ObjectId
@router.post("/answers")
async def save_answers(payload: AnswerRequest):

    answers_list = []
    total_marks = 0
    rating_values = []  # collect rating answers

    # Loop through each question + answer
    for qid, ans in zip(payload.question_ids, payload.answers):

        # Fetch question
        question = await db.questions.find_one({"_id": ObjectId(qid)})
        if not question:
            continue

        q_type = question.get("type")
        correct_index = question.get("correct_index")

        # ============================
        # 1) HANDLE RATING QUESTIONS
        # ============================
        if q_type == "rating":
            rating_values.append(ans)    # store rating
            mark = 0                     # rating gives no direct mark
        else:
            # ==============================
            # 2) HANDLE MCQ QUESTIONS (text/image)
            # ==============================
            mark = 1 if ans == correct_index else 0
            total_marks += mark

        # Append answer details
        answers_list.append({
            "question_id": qid,
            "answer_value": ans,
            "correct_index": correct_index,
            "type": q_type,
            "mark": mark
        })

    # ==============================
    # 3) CALCULATE RATING AVERAGE
    # ==============================
    if rating_values:
        rating_avg = sum(rating_values) / len(rating_values)
        total_marks += rating_avg
    else:
        rating_avg = 0

    # Default attempt = 0
    attempt = getattr(payload, "attempt", 0)

    # Final document
    document = {
        "student_id": payload.student_id,
        "category": payload.category,
        "attempt": attempt,
        "answers": answers_list,
        "rating_average": rating_avg,
        "total_marks": total_marks,
        "timestamp": datetime.now(timezone.utc)
    }

    result = await db.answers.insert_one(document)

    return {
        "status_code": 200,
        "message": "All answers saved",
        "answer_sheet_id": str(result.inserted_id),
        "rating_average": rating_avg,
        "total_marks": total_marks
    }

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
career_map = {
    "musical": "Musician, Composer, Singer, Sound Engineer",
    "logical-mathematical": "Scientist, Engineer, Mathematician, Data Analyst",
    "verbal-linguistic": "Writer, Journalist, Teacher, Lawyer",
    "bodily-kinesthetic": "Athlete, Dancer, Physical Therapist, Surgeon",
    "visual-spatial": "Architect, Designer, Artist, Pilot",
    "interpersonal": "Teacher, Counselor, Manager, Salesperson",
    "intrapersonal": "Psychologist, Philosopher, Writer",
    "naturalistic": "Biologist, Environmentalist, Farmer, Veterinarian"
}
@router.post("/analyze-career/{student_id}")
async def analyze_career(student_id: str):
    answers_cursor = db.answers.find({"student_id": student_id})
    answers = await answers_cursor.to_list(length=None)

    if not answers:
        raise HTTPException(status_code=404, detail="No answers found for this student")
    scores, counts = {}, {}
    for ans in answers:
        cat = ans["category"]
        scores[cat] = scores.get(cat, 0) + ans["answer_value"]
        counts[cat] = counts.get(cat, 0) + 1

    for cat in scores:
        scores[cat] = round(scores[cat] / counts[cat], 2)

    top_3 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cat = top_3[0][0]
    recommended_career = career_map.get(top_cat, "No career mapped")

    await db.students.update_one(
        {"student_id": student_id},
        {"$set": {"career": recommended_career}}
    )

    await db.career_analysis.update_one(
        {"student_id": student_id},
        {
            "$set": {
                "scores": scores,
                "top_category": top_cat,
                "recommended_career": recommended_career,
                "timestamp": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    insights = [f"{cat}: Strong inclination towards {cat.lower()} intelligence." for cat, _ in top_3]
    
    careers = [f"{cat} ➔ {career_map.get(cat.strip().lower(), 'Unknown Career')}" for cat, _ in top_3]


    return {
        "status_code": 200,
        "student_id": student_id,
        "scores": scores,
        "top_category": top_cat,
        "recommended_career": recommended_career,
        "personality_insights": insights,
        "career_suggestions": careers
    }

@router.get("/career-results/{student_id}")
async def get_career_results(student_id: str):
    record = await db.career_analysis.find_one({"student_id": student_id})
    if not record:
        raise HTTPException(status_code=404, detail="No analysis found for this student")
    record["_id"] = str(record["_id"])
    return record
