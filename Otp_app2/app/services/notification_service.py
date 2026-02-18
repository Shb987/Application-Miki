import uuid
import datetime
import httpx
from bson import ObjectId
from app.core.settings import settings


# OneSignal Credentials
ONESIGNAL_APP_ID = settings.ONESIGNAL_APP_ID
ONESIGNAL_API_KEY = settings.ONESIGNAL_API_KEY

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

async def broadcast_notification(db, title: str, message: str, notification_type: str, extra_data: dict = None):
    """
    Broadcasts a notification to ALL students via OneSignal and saves to their MongoDB history.
    """
    
    # 1. Fetch all student IDs
    cursor = db.students.find({}, {"_id": 1})
    students = await cursor.to_list(length=None)
    student_ids = [str(s["_id"]) for s in students]

    if not student_ids:
        print("⚠️ No students found to notify.")
        return

    # 2. Save to MongoDB (History) for each student
    # Note: For very large student bases (10k+), this should be optimized with insert_many
    notifications_to_insert = []
    now = datetime.datetime.utcnow()
    
    for s_id in student_ids:
        # Start with extra data to avoid overwriting core fields later
        notif = {}
        if extra_data:
            notif.update(extra_data)
        
        # Core fields take priority
        notif.update({
            "student_id": s_id,
            "title": title,
            "message": message,
            "type": notification_type,
            "is_read": False,
            "created_at": now
        })
        notifications_to_insert.append(notif)
    
    if notifications_to_insert:
        await db.notifications.insert_many(notifications_to_insert)
        print(f"✅ Saved notification history for {len(notifications_to_insert)} students.")

    # 3. Push to OneSignal (Universal Broadcast)
    if not ONESIGNAL_APP_ID or not ONESIGNAL_API_KEY:
        print("⚠️ OneSignal credentials not found. Skipping universal push.")
        return

    url = "https://onesignal.com/api/v1/notifications"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {ONESIGNAL_API_KEY}"
    }
    
    onesignal_data = {
        "type": notification_type,
        "is_broadcast": True
    }
    if extra_data:
        onesignal_data.update(extra_data)

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "included_segments": ["All"], # Target everyone
        "headings": {"en": title},
        "contents": {"en": message},
        "data": onesignal_data
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                print(f"✅ OneSignal Broadcast Sent Successfully: {response.json()}")
            else:
                print(f"❌ OneSignal Broadcast Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ OneSignal Broadcast Failed: {e}")