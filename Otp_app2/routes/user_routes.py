from fastapi import APIRouter
from models.user_models import UserCreate, Student,UserTypeRequest
from models.answer_models import AnswerRequest
from core.database import db
from datetime import datetime, timedelta, timezone
from fastapi import Query
from typing import Dict, List
from models.recommendation_models import Recommendation
from fastapi import HTTPException



router = APIRouter(tags=["User"])

async def generate_student_id():
    count = await db.students.count_documents({})
    return f"STU{str(count+1).zfill(4)}"   # STU0001, STU0002, etc.

from fastapi import Query

@router.post("/register-student")
async def register_student(
    data: Student,
    parent_mobile: str = Query(..., description="Parent mobile number")
):
    # Generate unique student_id
    student_id = await generate_student_id()

    student_doc = {
        "student_id": student_id,
        "student_name": data.student_name,
        "dob": data.dob,
        "student_class": data.student_class,
        'age':data.age,
        "address": data.address,
        "guardian_name": data.guardian_name,
        "created_at": datetime.now(timezone.utc),
        "is_user": False   # 👈 new field, student not a user yet

    }

    # Insert into students collection
    await db.students.insert_one(student_doc)

    # Link parent → student in user table
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
    """Convert ObjectId and other non-JSON types into str"""
    if not doc:
        return doc
    doc["_id"] = str(doc["_id"])
    return doc

# ✅ Get parent-student details by parent number
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

    return {
        "status_code": 200,
        "parent_number": mobile_number,
        "students": students
    }

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


  # ✅ Get all Login Attempts (OTP table)
@router.get("/student_questions")
async def get_questions_by_age(
    age: int = Query(..., description="Student age to filter questions")
):
    """
    Fetch questions filtered by age range and return grouped by category.
    """
    # Query: only questions where age_min <= age <= age_max
    query = {
        "$and": [
            {"age_min": {"$lte": age}},   # age >= min
            {"age_max": {"$gte": age}}    # age <= max
        ]
    }
    cursor = db.questions.find(query)
    questions = [clean_mongo_doc(doc) for doc in await cursor.to_list(length=None)]
    # Group by category
    grouped: Dict[str, List[dict]] = {}
    for q in questions:
        cat = q["category"]
        grouped.setdefault(cat, []).append({
            "id": str(q["_id"]),  # Include ObjectId as string
            "text": q["text"],
            "options": q.get("options", []),
            "answer": q.get("answer")
        })


    return {
        "status_code": 200,
        "age": age,
        "categories": grouped
    }

# ✅ Get all students (for Admin Dashboard)
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
async def save_answer(payload: AnswerRequest):
    """
    Save a student's answer (rating) for a question.
    """

    # Validate question
    question = await db.questions.find_one({"_id": ObjectId(payload.question_id)})
    if not question:
        return {"status_code": 404, "message": "Question not found"}

    # Build answer document
    answer_doc = {
        "student_id": payload.student_id,
        "category": question["category"],   # pulled from question
        "question_id": str(question["_id"]),
        "answer_value": payload.answer_value,
        "timestamp": datetime.now(timezone.utc)
    }

    result = await db.answers.insert_one(answer_doc)

    return {
        "status_code": 200,
        "message": "Answer saved",
        "answer_id": str(result.inserted_id)
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


async def determine_career(student_id: str) -> str:
    student = await db.students.find_one({"student_id": student_id})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    career = student.get("career")
    if not career:
        raise HTTPException(status_code=404, detail="Career not set for this student")

    return career

# ✅ Add or update recommendations for a career
@router.post("/recommendations")
async def add_recommendations(data: Recommendation):
    await db.recommendations.update_one(
        {"career": data.career, "student_id": data.student_id},  
        {
            "$set": {
                "tutorials": data.tutorials,
                "videos": data.videos,
                "student_id": data.student_id,
                "career": data.career
            }
        },
        upsert=True
    )
    return {
        "status_code": 200,
        "message": f"Recommendations updated for student {data.student_id} ({data.career})"
    }
# ✅ Get recommendations for a student based on answers → career
@router.get("/recommend/{student_id}")
async def get_recommendations(student_id: str):
    student = await db.students.find_one({"student_id": student_id})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    career = student.get("career", None)
    if not career:
        return {
            "status_code": 200,
            "student_id": student_id,
            "career": None,
            "recommendations": {"tutorials": [], "videos": []},
            "message": "Career not set for this student"
        }

    doc = await db.recommendations.find_one({"student_id": student_id, "career": career})
    
    if not doc:
        return {
            "status_code": 200,
            "student_id": student_id,
            "career": career,
            "recommendations": {"tutorials": [], "videos": []}
        }

    return {
        "status_code": 200,
        "student_id": student_id,
        "career": career,
        "recommendations": {
            "tutorials": doc.get("tutorials", []),
            "videos": doc.get("videos", [])
        }
    }

