from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
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
    target_board = board or syllabus

    # Auto-resolve student's syllabus/board if student_id is provided and board is not specified
    if not target_board and student_id:
        student = None
        try:
            if len(student_id) == 24:
                student = await db.students.find_one({"_id": ObjectId(student_id)})
        except Exception:
            pass

        if not student:
            student = await db.students.find_one({"student_id": student_id})
        if not student:
            student = await db.students.find_one({"mobile_number": student_id})

        if student:
            target_board = student.get("syllabus") or student.get("board")

    query = {"student_class": str(student_class)}

    if target_board and target_board.strip():
        b_clean = target_board.strip()
        if b_clean.upper() == "NCERT":
            query["$or"] = [
                {"board": {"$regex": "^NCERT$", "$options": "i"}},
                {"board": {"$exists": False}},
                {"board": None},
                {"board": ""}
            ]
        else:
            query["board"] = {"$regex": f"^{b_clean}$", "$options": "i"}

    cursor = db.tutorials.find(query)
    tutorials = await cursor.to_list(length=100)

    for t in tutorials:
        t["_id"] = str(t["_id"])

    return tutorials
