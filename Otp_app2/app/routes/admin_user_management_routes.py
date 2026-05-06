from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Optional, Dict, Any
from bson import ObjectId
from datetime import datetime, timezone

from app.core.database import db
from app.utils.admin_auth import get_current_admin

router = APIRouter(tags=["User Management - Admin"])


def serialize(doc: dict) -> dict:
    """Convert MongoDB ObjectId and datetime fields to JSON-safe types."""
    if not doc:
        return {}
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, list):
            result[k] = [str(i) if isinstance(i, ObjectId) else i for i in v]
        elif isinstance(v, datetime):
            result[k] = v.isoformat() + "Z" if v.tzinfo is None else v.isoformat()
        else:
            result[k] = v
    return result


# ──────────────────────────────────────────────────────────────
# STUDENTS
# ──────────────────────────────────────────────────────────────

@router.get("/admin-panel/users/students")
async def search_students(
    name: Optional[str] = Query(None, description="Filter by student name (partial match)"),
    student_class: Optional[str] = Query(None, description="Filter by class (e.g. '5')"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_admin: dict = Depends(get_current_admin)
):
    """Search/list all students with optional filters."""
    query: Dict[str, Any] = {}
    if name:
        query["student_name"] = {"$regex": name, "$options": "i"}
    if student_class:
        query["student_class"] = student_class

    total = await db.students.count_documents(query)
    cursor = db.students.find(query).sort("created_at", -1).skip(skip).limit(limit)
    students = await cursor.to_list(length=limit)

    return {
        "status": "success",
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [serialize(s) for s in students]
    }


@router.get("/admin-panel/users/student/{student_id}")
async def get_student_profile(
    student_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Fetch a full student profile including:
    - Basic info (name, class, DOB, guardian)
    - Latest career analysis
    - Quiz attempt count
    - Intelligence test completion status
    """
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Career analysis (latest)
    career = await db.career_analyzer.find_one(
        {"student_id": student_id},
        sort=[("attempt", -1)]
    )

    # Quiz submissions count
    quiz_count = await db.quiz_submissions.count_documents({"student_id": student_id})

    # Intelligence answers (latest attempt)
    answers_doc = await db.answers.find_one({"student_id": s_oid})
    latest_attempt = None
    if answers_doc:
        attempts = answers_doc.get("attempts", [])
        if attempts:
            latest_attempt = attempts[-1]
            # Remove heavy answers list from response to keep it light
            for cat in latest_attempt.get("categories", []):
                cat.pop("answers", None)

    return {
        "status": "success",
        "data": {
            "student": serialize(student),
            "career": {
                "top_category": career.get("top_category") if career else None,
                "recommended_career": career.get("recommended_career") if career else None,
                "percentages": career.get("percentages") if career else {},
                "attempt": career.get("attempt") if career else None,
            },
            "quiz_attempts": quiz_count,
            "intelligence_test": latest_attempt
        }
    }


@router.delete("/admin-panel/users/student/{student_id}")
async def delete_student(
    student_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Permanently delete a student record and unlink from parent.
    Also removes answers, career analysis data for this student.
    """
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Unlink from parents
    await db.usertable.update_many(
        {"student_ids": s_oid},
        {"$pull": {"student_ids": s_oid}}
    )
    # Unlink from student-type users
    await db.usertable.update_many(
        {"student_id": s_oid},
        {"$unset": {"student_id": ""}}
    )

    # Remove associated data
    await db.answers.delete_many({"student_id": s_oid})
    await db.career_analyzer.delete_many({"student_id": student_id})
    await db.notifications.delete_many({"student_id": student_id})

    # Delete the student
    await db.students.delete_one({"_id": s_oid})

    return {"status": "success", "message": f"Student {student_id} deleted successfully"}


@router.patch("/admin-panel/users/student/{student_id}/deactivate")
async def deactivate_student(
    student_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Soft-deactivate a student (sets is_active=False)."""
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    result = await db.students.update_one(
        {"_id": s_oid},
        {"$set": {"is_active": False, "deactivated_at": datetime.now(timezone.utc)}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"status": "success", "message": "Student deactivated"}


class QuotaUpdate(BaseModel):
    bucket: str
    new_value: int

@router.patch("/admin-panel/users/student/{student_id}/quotas")
async def update_student_quotas(
    student_id: str,
    payload: QuotaUpdate,
    current_admin: dict = Depends(get_current_admin)
):
    """Manually update a student's usage quota."""
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")
        
    allowed_buckets = ["tutor_balance_qs", "exam_balance", "class_balance", "voice_balance_mins"]
    if payload.bucket not in allowed_buckets:
        raise HTTPException(status_code=400, detail="Invalid bucket name")
        
    if payload.new_value < 0:
        raise HTTPException(status_code=400, detail="Quota cannot be negative")

    result = await db.students.update_one(
        {"_id": s_oid},
        {"$set": {f"usage_buckets.{payload.bucket}": payload.new_value}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")
        
    return {"status": "success", "message": f"Updated {payload.bucket} to {payload.new_value}"}


# ──────────────────────────────────────────────────────────────
# PARENTS
# ──────────────────────────────────────────────────────────────

@router.get("/admin-panel/users/parents")
async def list_parents(
    search: Optional[str] = Query(None, description="Search by parent mobile"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_admin: dict = Depends(get_current_admin)
):
    """List all parents with their linked student names and join dates."""
    query = {"usertype": "parent"}
    if search:
        query["mobile_number"] = {"$regex": search, "$options": "i"}

    total = await db.usertable.count_documents(query)
    cursor = db.usertable.find(query).sort("created_at", -1).skip(skip).limit(limit)
    parents = await cursor.to_list(length=limit)

    # 1️⃣ Collect all student IDs for bulk fetch
    all_student_ids = []
    for p in parents:
        all_student_ids.extend(p.get("student_ids", []))
    
    # Remove duplicates
    all_student_ids = list(set(all_student_ids))

    # 2️⃣ Fetch student names
    student_map = {}
    if all_student_ids:
        s_cursor = db.students.find({"_id": {"$in": all_student_ids}}, {"_id": 1, "student_name": 1})
        async for s in s_cursor:
            student_map[str(s["_id"])] = s.get("student_name", "Unknown")

    # 3️⃣ Build result
    result = []
    for p in parents:
        p_data = serialize(p)
        
        # Resolve student names
        s_ids = p.get("student_ids", [])
        p_data["student_names"] = [student_map.get(str(sid), "Unknown") for sid in s_ids]
        p_data["student_count"] = len(s_ids)
        result.append(p_data)

    return {
        "status": "success",
        "total": total,
        "data": result
    }


@router.delete("/admin-panel/users/parent/{mobile}")
async def delete_parent(
    mobile: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Remove a parent record from usertable."""
    existing = await db.usertable.find_one({"mobile_number": mobile})
    if not existing:
        raise HTTPException(status_code=404, detail="Parent not found")
    await db.usertable.delete_one({"mobile_number": mobile})
    return {"status": "success", "message": f"Parent {mobile} removed"}


# ──────────────────────────────────────────────────────────────
# DISTINCT CLASS LIST (for filters)
# ──────────────────────────────────────────────────────────────

@router.get("/admin-panel/users/classes")
async def get_available_classes(current_admin: dict = Depends(get_current_admin)):
    """Returns the distinct student classes present in DB (for filter dropdowns)."""
    classes = await db.students.distinct("student_class")
    try:
        classes_sorted = sorted(classes, key=lambda x: int(str(x)))
    except Exception:
        classes_sorted = sorted(classes)
    return {"status": "success", "classes": classes_sorted}
