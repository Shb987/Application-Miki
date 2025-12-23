# services/notification_service.py
import uuid
import datetime

async def create_notification(db, user_id: str, title: str, message: str, type: str):
    notification = {
        "notification_id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": type,  # evaluation_completed, marks_generated, etc
        "is_read": False,
        "created_at": datetime.datetime.utcnow()
    }

    await db.notifications.insert_one(notification)
    return notification
