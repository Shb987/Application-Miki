from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Optional, Dict, Any
from bson import ObjectId
from datetime import datetime, timezone

from app.core.database import db
from app.utils.admin_auth import get_current_admin
from app.services.notification_service import broadcast_notification, create_notification

router = APIRouter(tags=["Notifications - Admin"])


# ──────────────────────────────────────────────────────────────
# BROADCAST TO ALL USERS
# ──────────────────────────────────────────────────────────────

@router.post("/admin-panel/notifications/broadcast")
async def broadcast_to_all(
    payload: Dict[str, Any] = Body(...),
    current_admin: dict = Depends(get_current_admin)
):
    """
    Send a push notification to ALL registered users.
    Body: { title, message, type }
    """
    title = payload.get("title", "").strip()
    message = payload.get("message", "").strip()
    notification_type = payload.get("type", "broadcast")

    if not title or not message:
        raise HTTPException(status_code=400, detail="title and message are required")

    # Count students for the response
    student_count = await db.students.count_documents({})

    # Fire broadcast (saves to MongoDB + sends OneSignal push)
    await broadcast_notification(db, title, message, notification_type)

    # Log the broadcast
    await db.broadcast_logs.insert_one({
        "title": title,
        "message": message,
        "type": notification_type,
        "target": "all",
        "target_class": None,
        "recipient_count": student_count,
        "sent_by": current_admin.get("sub", "admin"),
        "created_at": datetime.now(timezone.utc)
    })

    return {
        "status": "success",
        "message": f"Broadcast sent to {student_count} students",
        "recipient_count": student_count
    }


# ──────────────────────────────────────────────────────────────
# BROADCAST TO A SPECIFIC CLASS
# ──────────────────────────────────────────────────────────────

@router.post("/admin-panel/notifications/broadcast-class")
async def broadcast_to_class(
    payload: Dict[str, Any] = Body(...),
    current_admin: dict = Depends(get_current_admin)
):
    """
    Send a push notification to students in a specific class.
    Body: { title, message, type, student_class }
    """
    title = payload.get("title", "").strip()
    message = payload.get("message", "").strip()
    notification_type = payload.get("type", "class_broadcast")
    student_class = payload.get("student_class", "").strip()

    if not title or not message or not student_class:
        raise HTTPException(status_code=400, detail="title, message and student_class are required")

    # Fetch students in this class
    cursor = db.students.find({"student_class": student_class}, {"_id": 1})
    students = await cursor.to_list(length=None)

    if not students:
        raise HTTPException(status_code=404, detail=f"No students found in class {student_class}")

    # Send individual notifications (reuse create_notification which handles OneSignal targeting)
    for student in students:
        await create_notification(
            db,
            user_id=str(student["_id"]),
            title=title,
            message=message,
            notification_type=notification_type
        )

    recipient_count = len(students)

    # Log the broadcast
    await db.broadcast_logs.insert_one({
        "title": title,
        "message": message,
        "type": notification_type,
        "target": "class",
        "target_class": student_class,
        "recipient_count": recipient_count,
        "sent_by": current_admin.get("sub", "admin"),
        "created_at": datetime.now(timezone.utc)
    })

    return {
        "status": "success",
        "message": f"Notification sent to {recipient_count} students in class {student_class}",
        "recipient_count": recipient_count
    }


# ──────────────────────────────────────────────────────────────
# NOTIFICATION HISTORY
# ──────────────────────────────────────────────────────────────

@router.get("/admin-panel/notifications/history")
async def get_notification_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    notification_type: Optional[str] = Query(None),
    current_admin: dict = Depends(get_current_admin)
):
    """Get paginated broadcast history from broadcast_logs collection."""
    query: Dict[str, Any] = {}
    if notification_type:
        query["type"] = notification_type

    total = await db.broadcast_logs.count_documents(query)
    cursor = db.broadcast_logs.find(query).sort("created_at", -1).skip(skip).limit(limit)
    logs = await cursor.to_list(length=limit)

    for log in logs:
        log["_id"] = str(log["_id"])
        if isinstance(log.get("created_at"), datetime):
            log["created_at"] = log["created_at"].isoformat() + "Z"

    return {
        "status": "success",
        "total": total,
        "data": logs
    }


# ──────────────────────────────────────────────────────────────
# NOTIFICATION STATS
# ──────────────────────────────────────────────────────────────

@router.get("/admin-panel/notifications/stats")
async def get_notification_stats(current_admin: dict = Depends(get_current_admin)):
    """Returns count of broadcasts sent today, this week, and this month."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    today_count = await db.broadcast_logs.count_documents({"created_at": {"$gte": today_start}})
    week_count = await db.broadcast_logs.count_documents({"created_at": {"$gte": week_start}})
    month_count = await db.broadcast_logs.count_documents({"created_at": {"$gte": month_start}})

    return {
        "status": "success",
        "data": {
            "today": today_count,
            "this_week": week_count,
            "this_month": month_count
        }
    }


# ──────────────────────────────────────────────────────────────
# AVAILABLE CLASSES (for target dropdown)
# ──────────────────────────────────────────────────────────────

@router.get("/admin-panel/notifications/classes")
async def get_classes_for_notifications(current_admin: dict = Depends(get_current_admin)):
    classes = await db.students.distinct("student_class")
    try:
        classes_sorted = sorted(classes, key=lambda x: int(str(x)))
    except Exception:
        classes_sorted = sorted(classes)
    return {"status": "success", "classes": classes_sorted}
