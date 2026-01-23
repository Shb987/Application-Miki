import uuid
import datetime
import os
import httpx
from bson import ObjectId


# OneSignal Credentials
ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID")
ONESIGNAL_API_KEY = os.getenv("ONESIGNAL_API_KEY")

async def create_notification(db, user_id: str, title: str, message: str, notification_type: str, extra_data: dict = None):
    """
    Creates a notification in MongoDB and sends it via OneSignal.
    
    Args:
        db: MongoDB database instance
        user_id: The ID of the student/user to receive the notification.
        title: Notification Title
        message: Notification Body
        notification_type: Type of notification (e.g., 'evaluation_completed')
        extra_data: Optional dictionary with additional data (e.g., evaluation_id)
    """
    
    # 1. Save to MongoDB (History)

    notification = {

        "student_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "is_read": False,
        "created_at": datetime.datetime.utcnow()
    }

    # Merge extra data if provided
    if extra_data:
        notification.update(extra_data)

    result = await db.notifications.insert_one(notification)

    # ✅ MongoDB-generated notification id
    notification_id = str(result.inserted_id)

    # 2. Push to OneSignal
    if not ONESIGNAL_APP_ID or not ONESIGNAL_API_KEY:
        print("⚠️ OneSignal credentials not found in .env. Skipping push notification.")
        return notification

    url = "https://onesignal.com/api/v1/notifications"
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {ONESIGNAL_API_KEY}"
    }
    
    # Payload for OneSignal
    # We target the user by their 'user_id' (student_id) which should be set as 'external_user_id' in the App.
    onesignal_data = {
        "type": notification_type,
        "student_id": user_id,
        "notification_id": notification_id
    }
    if extra_data:
        onesignal_data.update(extra_data)

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "include_external_user_ids": [user_id], 
        "headings": {"en": title},
        "contents": {"en": message},
        "data": onesignal_data
    }
    
    # Fire and Forget (Async)
    # We catch exceptions so as not to block the main thread or error out the request
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            print(response)
            
            if response.status_code == 200:
                print(f"✅ OneSignal Notification Sent to {user_id}: {response.json()}")
            else:
                print(f"❌ OneSignal Error {response.status_code}: {response.text}")
                
    except Exception as e:
        print(f"❌ OneSignal Push Failed: {e}")

    return notification