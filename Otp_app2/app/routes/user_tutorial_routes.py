from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from bson import ObjectId
import re
from app.core.database import db

router = APIRouter(prefix="/user/tutorials")

async def fetch_student_by_id(student_id: str) -> Optional[dict]:
    if not student_id:
        return None
    s_clean = str(student_id).strip()
    student = None
    try:
        if ObjectId.is_valid(s_clean):
            student = await db.students.find_one({"_id": ObjectId(s_clean)})
    except Exception:
        pass
    if not student:
        student = await db.students.find_one({"_id": s_clean})
    if not student:
        student = await db.students.find_one({"student_id": s_clean})
    if not student:
        student = await db.students.find_one({"id": s_clean})
    if not student:
        student = await db.students.find_one({"mobile_number": s_clean})

    if not student:
        user_doc = None
        try:
            if ObjectId.is_valid(s_clean):
                user_doc = await db.usertable.find_one({"_id": ObjectId(s_clean)})
        except Exception:
            pass
        if not user_doc:
            user_doc = await db.usertable.find_one({"_id": s_clean})
        if not user_doc:
            user_doc = await db.usertable.find_one({"mobile_number": s_clean})

        if user_doc:
            st_id = user_doc.get("student_id") or user_doc.get("student_oid")
            if st_id and str(st_id) != s_clean:
                st_found = await fetch_student_by_id(str(st_id))
                if st_found:
                    return st_found
            return user_doc

    return student

def get_student_board_value(student: dict) -> str:
    if not student:
        return "NCERT"
    
    possible_keys = ["syllabus", "board", "category", "curriculum", "school_board", "education_board"]
    val = None
    for k in possible_keys:
        if student.get(k):
            val = student.get(k)
            break

    if val:
        v_str = str(val).strip().upper()
        if "SCERT" in v_str or "STATE" in v_str or "KERALA" in v_str:
            return "SCERT"
        if "NCERT" in v_str or "CBSE" in v_str:
            return "NCERT"
        return v_str
        
    return "NCERT"

@router.get("/")
async def get_user_tutorials(
    student_id: str = Query(..., description="Student ID (Required)"),
    student_class: Optional[str] = Query(None, description="Class/Standard (e.g. '4', 'Class 4')")
):
    """
    Get tutorials for a specific student.
    student_id is required. Checks whether student is NCERT or SCERT and shows board-specific contents only.
    """
    if not student_id or not str(student_id).strip():
        raise HTTPException(status_code=400, detail="student_id is required")

    student = await fetch_student_by_id(student_id)
    if not student:
        raise HTTPException(status_code=404, detail=f"Student not found with ID: {student_id}")

    target_class = student_class
    if not target_class:
        target_class = student.get("student_class") or student.get("class") or student.get("standard")

    if not target_class:
        raise HTTPException(status_code=400, detail="student_class is required or must be set in student profile")

    c_str = str(target_class).strip()
    c_digits = "".join([ch for ch in c_str if ch.isdigit()]) or c_str

    class_match_patterns = [
        {"student_class": c_str},
        {"student_class": c_digits},
        {"student_class": f"Class {c_digits}"},
        {"student_class": f"class {c_digits}"},
        {"student_class": {"$regex": f"^Class\\s*{c_digits}$|^{c_digits}$", "$options": "i"}}
    ]
    if c_digits.isdigit():
        class_match_patterns.append({"student_class": int(c_digits)})

    class_query = {"$or": class_match_patterns}

    target_board = get_student_board_value(student)

    if target_board.upper() == "SCERT":
        board_query = {
            "$or": [
                {"board": {"$regex": "SCERT|State|Kerala", "$options": "i"}},
                {"category": {"$regex": "SCERT|State|Kerala", "$options": "i"}},
                {"syllabus": {"$regex": "SCERT|State|Kerala", "$options": "i"}}
            ]
        }
    else:
        board_query = {
            "$or": [
                {"board": {"$regex": "NCERT|CBSE", "$options": "i"}},
                {"category": {"$regex": "NCERT|CBSE", "$options": "i"}},
                {"syllabus": {"$regex": "NCERT|CBSE", "$options": "i"}},
                {"board": {"$exists": False}},
                {"board": None},
                {"board": ""}
            ]
        }

    final_query = {"$and": [class_query, board_query]}

    cursor = db.tutorials.find(final_query)
    tutorials = await cursor.to_list(length=100)

    for t in tutorials:
        t["_id"] = str(t["_id"])

    return tutorials


