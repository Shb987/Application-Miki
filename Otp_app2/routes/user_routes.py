from fastapi import APIRouter
from models.user_models import UserCreate, Student,UserTypeRequest
from core.database import db
from datetime import datetime, timedelta, timezone
from fastapi import Query


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




# ✅ Get all students (for Admin Dashboard)
@router.get("/get_students")
async def get_students():
    cursor = db.students.find({}, {"_id": 0})  # exclude MongoDB _id
    students = await cursor.to_list(length=None)
    return {
        "status_code": 200,
        "students": students
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


  

