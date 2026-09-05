from fastapi import APIRouter
import re
from app.core.database import db

router = APIRouter(prefix="/user/tutorials")

@router.get("/")
async def get_user_tutorials(student_class: str):
    """
    Get tutorials for a specific class.
    Matches student_class flexibly (e.g. "4", "Class 4", or 4).
    """
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

    cursor = db.tutorials.find(query)
    tutorials = await cursor.to_list(length=100)

    for t in tutorials:
        t["_id"] = str(t["_id"])

    return tutorials
