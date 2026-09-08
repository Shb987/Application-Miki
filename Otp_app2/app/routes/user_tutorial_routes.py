from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from bson import ObjectId
import re
from app.core.database import db

router = APIRouter(prefix="/user/tutorials")

async def fetch_student_by_id(student_id: str) -> Optional[dict]:
    if not student_id:
        return None
    student = None
    try:
        if ObjectId.is_valid(student_id):
            student = await db.students.find_one({"_id": ObjectId(student_id)})
    except Exception:
        pass
    if not student:
        student = await db.students.find_one({"_id": student_id})
    if not student:
        student = await db.students.find_one({"student_id": student_id})
    return student

def get_student_board_value(student: dict) -> Optional[str]:
    if not student:
        return None
    val = (
        student.get("syllabus") or 
        student.get("board") or 
        student.get("category") or 
        student.get("curriculum")
    )
    if val:
        v_str = str(val).strip().upper()
        if v_str in ["NCERT", "CBSE"]:
            return "NCERT"
        elif v_str in ["SCERT", "STATE", "KERALA"]:
            return "SCERT"
        return v_str
    return None

@router.get("/")
async def get_user_tutorials(
    student_class: Optional[str] = Query(None, description="Class/Standard (e.g. '4', 'Class 4')"),
    student_id: Optional[str] = Query(None, description="Student ID to automatically fetch student class and NCERT/SCERT syllabus")
):
    """
    Get tutorials for a specific class.
    If student_id is provided, checks whether student is NCERT or SCERT and shows board-specific contents only.
    """
    target_class = student_class
    target_board = None

    if student_id:
        student = await fetch_student_by_id(student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
            
        if not target_class:
            target_class = student.get("student_class") or student.get("class") or student.get("standard")
            
        target_board = get_student_board_value(student)

    if not target_class:
        raise HTTPException(status_code=400, detail="student_class or valid student_id is required")

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

    and_conditions = [class_query]

    if target_board:
        if target_board.upper() in ["SCERT", "STATE", "KERALA"]:
            and_conditions.append({
                "$or": [
                    {"board": {"$regex": "^(SCERT|State|Kerala)$", "$options": "i"}},
                    {"category": {"$regex": "^SCERT$", "$options": "i"}}
                ]
            })
        elif target_board.upper() in ["NCERT", "CBSE"]:
            and_conditions.append({
                "$or": [
                    {"board": {"$regex": "^(NCERT|CBSE)$", "$options": "i"}},
                    {"category": {"$regex": "^NCERT$", "$options": "i"}},
                    {"board": {"$exists": False}},
                    {"board": None},
                    {"board": ""}
                ]
            })
        else:
            and_conditions.append({
                "$or": [
                    {"board": {"$regex": f"^{re.escape(target_board)}$", "$options": "i"}},
                    {"category": {"$regex": f"^{re.escape(target_board)}$", "$options": "i"}}
                ]
            })

    final_query = {"$and": and_conditions} if len(and_conditions) > 1 else class_query

    cursor = db.tutorials.find(final_query)
    tutorials = await cursor.to_list(length=100)

    for t in tutorials:
        t["_id"] = str(t["_id"])

    return tutorials

