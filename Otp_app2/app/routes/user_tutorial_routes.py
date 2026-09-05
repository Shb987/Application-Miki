from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import re
from bson import ObjectId
from app.core.database import db

router = APIRouter(prefix="/user/tutorials")

@router.get("/")
async def get_user_tutorials(
    student_class: str,
    board: Optional[str] = Query(None, description="Board / Syllabus filter (e.g. NCERT or SCERT)"),
    syllabus: Optional[str] = Query(None, description="Alias for board filter"),
    student_id: Optional[str] = Query(None, description="Student ID to auto-resolve board/syllabus")
):
    """
    Get tutorials for a specific class and board (NCERT/SCERT).
    Shows SCERT tutorials for SCERT users and NCERT tutorials for NCERT users.
    """
    def sanitize(val: Optional[str]) -> Optional[str]:
        if not val or not isinstance(val, str):
            return None
        v = val.strip()
        if v.lower() in ["", "null", "none", "undefined", "string", "syllabus"]:
            return None
        return v

    clean_board = sanitize(board)
    clean_syllabus = sanitize(syllabus)
    clean_student_id = sanitize(student_id)

    target_board = clean_board or clean_syllabus

    # Auto-resolve student's syllabus/board if student_id is provided
    if clean_student_id:
        student = None
        try:
            if len(clean_student_id) == 24:
                student = await db.students.find_one({"_id": ObjectId(clean_student_id)})
        except Exception:
            pass

        if not student:
            student = await db.students.find_one({"student_id": clean_student_id})
        if not student:
            digits = "".join([ch for ch in clean_student_id if ch.isdigit()])
            if len(digits) >= 10:
                regex_pat = re.compile(rf"{digits[-10:]}$")
                student = await db.students.find_one({"mobile_number": regex_pat})

        if student:
            st_board = sanitize(student.get("syllabus")) or sanitize(student.get("board"))
            if st_board:
                target_board = st_board

    c_str = str(student_class).strip()
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

    query = {"$or": class_match_patterns}

    if target_board:
        b_clean = target_board.strip()
        if b_clean.upper() == "NCERT":
            board_condition = {
                "$or": [
                    {"board": {"$regex": "^NCERT$", "$options": "i"}},
                    {"board": {"$exists": False}},
                    {"board": None},
                    {"board": ""}
                ]
            }
        else:
            board_condition = {"board": {"$regex": f"^{re.escape(b_clean)}$", "$options": "i"}}

        query = {
            "$and": [
                {"$or": class_match_patterns},
                board_condition
            ]
        }

    cursor = db.tutorials.find(query)
    tutorials = await cursor.to_list(length=100)

    for t in tutorials:
        t["_id"] = str(t["_id"])

    return tutorials
