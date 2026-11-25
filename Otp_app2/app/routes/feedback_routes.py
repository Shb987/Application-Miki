from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.database import db
from app.utils.user_auth import get_current_user
from app.utils.admin_auth import get_current_admin

user_router = APIRouter(tags=["Feedback - User"])
admin_router = APIRouter(tags=["Feedback - Admin"])


class FeedbackCreate(BaseModel):
    message: Optional[str] = Field(None, description="Feedback message")
    feedback: Optional[str] = Field(None, description="Alias for feedback message")
    rating: Optional[int] = Field(None, ge=1, le=5)
    student_id: Optional[str] = None


class FeedbackStatusUpdate(BaseModel):
    status: str = Field(..., description="Status: new, reviewed, or resolved")


def _serialize_feedback(doc: dict) -> dict:
    created_at = doc.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    updated_at = doc.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()

    return {
        "id": str(doc["_id"]),
        "user_id": doc.get("user_id"),
        "student_id": doc.get("student_id"),
        "user_name": doc.get("user_name") or "User",
        "mobile_number": doc.get("mobile_number") or "",
        "user_type": doc.get("user_type") or "user",
        "message": doc.get("message") or "",
        "rating": doc.get("rating"),
        "status": doc.get("status") or "new",
        "created_at": created_at,
        "updated_at": updated_at,
    }


@user_router.post("/feedback")
async def submit_user_feedback(
    payload: FeedbackCreate,
    current_user: dict = Depends(get_current_user)
):
    """Submit user feedback from the mobile/user app."""
    msg = (payload.message or payload.feedback or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Feedback message is required")

    mobile = str(current_user.get("sub") or current_user.get("mobile_number") or "").strip()
    user_type = str(current_user.get("usertype") or current_user.get("role") or "user").strip()
    student_id = (payload.student_id or current_user.get("student_id") or current_user.get("_id") or "").strip()
    if student_id.lower() == "string":
        student_id = ""

    user_name = (
        current_user.get("student_name")
        or current_user.get("guardian_name")
        or current_user.get("name")
        or ""
    ).strip()

    # Enrich from students / usertable if needed
    if not user_name and student_id and ObjectId.is_valid(student_id):
        st = await db.students.find_one(
            {"_id": ObjectId(student_id)},
            {"student_name": 1, "guardian_name": 1, "mobile_number": 1, "student_phone": 1}
        )
        if st:
            user_name = (st.get("student_name") or st.get("guardian_name") or "").strip()
            if not mobile:
                mobile = str(st.get("mobile_number") or st.get("student_phone") or "").strip()

    user_id = ""
    if mobile:
        digits = "".join(c for c in mobile if c.isdigit())
        query = {"mobile_number": {"$regex": f"{digits[-10:]}$"}} if len(digits) >= 10 else {"mobile_number": mobile}
        user_doc = await db.usertable.find_one(query, {"_id": 1, "usertype": 1, "student_id": 1, "student_ids": 1})
        if user_doc:
            user_id = str(user_doc["_id"])
            if not user_type or user_type == "user":
                user_type = user_doc.get("usertype") or user_type
            if not student_id:
                if user_doc.get("student_id"):
                    student_id = str(user_doc["student_id"])
                elif user_doc.get("student_ids"):
                    student_id = str(user_doc["student_ids"][0])

    if not user_name:
        user_name = mobile or "App User"

    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "student_id": student_id,
        "user_name": user_name,
        "mobile_number": mobile,
        "user_type": user_type,
        "message": msg,
        "rating": payload.rating,
        "status": "new",
        "created_at": now,
        "updated_at": now,
    }

    res = await db.feedbacks.insert_one(doc)
    doc["_id"] = res.inserted_id

    return {
        "status": True,
        "message": "Feedback submitted successfully",
        "data": _serialize_feedback(doc),
    }


@admin_router.get("/feedbacks")
async def list_feedbacks(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_admin: dict = Depends(get_current_admin)
):
    """List user-submitted feedbacks for the admin panel."""
    query = {}
    if category and category.strip():
        query["category"] = category.strip().lower()
    if status and status.strip():
        query["status"] = status.strip().lower()
    if search and search.strip():
        regex = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"user_name": regex},
            {"mobile_number": regex},
            {"subject": regex},
            {"message": regex},
            {"category": regex},
        ]

    total = await db.feedbacks.count_documents(query)
    cursor = db.feedbacks.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)

    total_all = await db.feedbacks.count_documents({})
    new_count = await db.feedbacks.count_documents({"status": "new"})
    reviewed_count = await db.feedbacks.count_documents({"status": {"$in": ["reviewed", "resolved"]}})

    return {
        "status": True,
        "total": total,
        "stats": {
            "total": total_all,
            "new": new_count,
            "reviewed": reviewed_count,
        },
        "data": [_serialize_feedback(d) for d in docs],
    }


@admin_router.patch("/feedbacks/{feedback_id}/status")
async def update_feedback_status(
    feedback_id: str,
    payload: FeedbackStatusUpdate,
    current_admin: dict = Depends(get_current_admin)
):
    """Update feedback status (new, reviewed, resolved)."""
    if not ObjectId.is_valid(feedback_id):
        raise HTTPException(status_code=400, detail="Invalid feedback ID")

    new_status = payload.status.strip().lower()
    if new_status not in ("new", "reviewed", "resolved"):
        raise HTTPException(status_code=400, detail="Status must be 'new', 'reviewed', or 'resolved'")

    res = await db.feedbacks.update_one(
        {"_id": ObjectId(feedback_id)},
        {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc)}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Feedback not found")

    return {"status": True, "message": f"Feedback marked as {new_status}"}


@admin_router.delete("/feedbacks/{feedback_id}")
async def delete_feedback(
    feedback_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Delete a feedback entry."""
    if not ObjectId.is_valid(feedback_id):
        raise HTTPException(status_code=400, detail="Invalid feedback ID")

    res = await db.feedbacks.delete_one({"_id": ObjectId(feedback_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Feedback not found")

    return {"status": True, "message": "Feedback deleted successfully"}
