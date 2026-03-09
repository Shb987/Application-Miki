import uuid
import datetime
import httpx
from bson import ObjectId
from app.core.settings import settings


# OneSignal Credentials
ONESIGNAL_APP_ID = settings.ONESIGNAL_APP_ID
ONESIGNAL_API_KEY = settings.ONESIGNAL_API_KEY

async def create_notification(db, user_id: str, title: str, message: str, notification_type: str, extra_data: dict = None, priority: int = 10):
    """
    Creates a notification in MongoDB (per student) and sends it via OneSignal (targeting parent).
    """
    
    # 1. Save to MongoDB (History - Always per student)
    notification = {
        "student_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "is_read": False,
        "created_at": datetime.datetime.utcnow()
    }

    if extra_data:
        notification.update(extra_data)

    result = await db.notifications.insert_one(notification)
    notification_id = str(result.inserted_id)

    # 2. Push to OneSignal (Targeting Parent to avoid duplicates on shared phones)
    if not ONESIGNAL_APP_ID or not ONESIGNAL_API_KEY:
        print("⚠️ OneSignal credentials not found. Skipping push.")
        return notification

    # Find the linked users in usertable to get the correct targeting mobile numbers
    # We want to target the 'mobile_number' field for OneSignal
    target_ids = []
    
    if ObjectId.is_valid(user_id):
        cursor = db.usertable.find({
            "$or": [
                {"student_ids": {"$in": [ObjectId(user_id)]}, "usertype": "parent"},
                {"student_id": ObjectId(user_id), "usertype": "student"}
            ]
        }, {"mobile_number": 1})
        
        users = await cursor.to_list(length=None)
        target_ids = list(set([u["mobile_number"] for u in users if u.get("mobile_number")]))
    
    # Fallback to the user_id itself if no mobile numbers found in usertable
    if not target_ids:
        target_ids = [user_id]
    
    url = "https://onesignal.com/api/v1/notifications"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {ONESIGNAL_API_KEY}"
    }
    
    onesignal_data = {
        "type": notification_type,
        "student_id": user_id,
        "notification_id": notification_id
    }
    if extra_data:
        onesignal_data.update(extra_data)

    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "include_external_user_ids": target_ids,
        "channel_for_external_user_ids": "push",
        "headings": {"en": title},
        "contents": {"en": message},
        "priority": priority,
        "data": onesignal_data
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                print(f"✅ OneSignal Sent to targets {target_ids} for Student {user_id}: {response.json()}")
            else:
                print(f"❌ OneSignal Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ OneSignal Push Failed: {e}")

    return notification

async def broadcast_notification(db, title: str, message: str, notification_type: str, extra_data: dict = None, priority: int = 10):
    """
    Broadcasts a notification to ALL students in DB but deduplicates push notifications by Parent (Phone).
    """
    
    # 1. Fetch all student IDs
    cursor = db.students.find({}, {"_id": 1})
    students = await cursor.to_list(length=None)
    student_ids = [str(s["_id"]) for s in students]

    if not student_ids:
        print("⚠️ No students found to notify.")
        return

    # 2. Save to MongoDB (Individual History for every student)
    notifications_to_insert = []
    now = datetime.datetime.utcnow()
    
    for s_id in student_ids:
        notif = {}
        if extra_data:
            notif.update(extra_data)
        
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

    # 3. Push to OneSignal (Deduplicated per Parent/Phone)
    if not ONESIGNAL_APP_ID or not ONESIGNAL_API_KEY:
        print("⚠️ OneSignal credentials not found. Skipping push.")
        return

    # Get unique Mobile Numbers from usertable to avoid duplicate pushes
    # Includes parents linked to these students AND the students themselves
    s_oids = [ObjectId(sid) for sid in student_ids]
    
    unique_mobile_numbers = await db.usertable.distinct("mobile_number", {
        "$or": [
            {"student_ids": {"$in": s_oids}, "usertype": "parent"},
            {"student_id": {"$in": s_oids}, "usertype": "student"}
        ]
    })
    
    target_ids = [str(mn) for mn in unique_mobile_numbers if mn]

    if not target_ids:
        print("⚠️ No mobile numbers found in usertable to receive push notifications.")
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
        "include_external_user_ids": target_ids,
        "channel_for_external_user_ids": "push",
        "headings": {"en": title},
        "contents": {"en": message},
        "priority": priority,
        "data": onesignal_data
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                print(f"✅ Deduplicated OneSignal Broadcast Sent to {len(target_ids)} unique parents: {response.json()}")
            else:
                print(f"❌ OneSignal Broadcast Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ OneSignal Broadcast Failed: {e}")
