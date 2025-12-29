# services/notification_service.py
import uuid
import datetime
from firebase_admin import messaging
from bson import ObjectId

async def create_notification(db, user_id: str, title: str, message: str, type: str):
    # 1. Save to MongoDB (History)
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

    # 2. Push to Firebase (FCM)
    try:
        # We need to find the user's FCM token.
        # Check if user_id is a student_id or a mobile_number (parent).
        # Assuming user_id refers to 'student_id' based on previous context.
        
        # Strategy: 
        # A. If user_id is a student_id, find the parent (usertable) who owns this student.
        # as students usually don't have separate logins, they use parents login? 
        # OR if students have their own login, we check their record.
        
        # Based on user_routes, students are linked to 'usertable' via 'student_ids'.
        # Let's search for the user who HAS this student_id in their list or is the student.
        
        user_record = await db.usertable.find_one({"student_ids": user_id}) 
        if not user_record:
             # Fallback: maybe the user_id IS the unique ID of the usertable? 
             user_record = await db.usertable.find_one({"_id": ObjectId(user_id)}) if ObjectId.is_valid(user_id) else None

        if user_record and "fcm_token" in user_record:
            fcm_token = user_record["fcm_token"]
            
            # Construct Message
            message_payload = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=message,
                ),
                data={
                    "type": type,
                    "student_id": user_id,
                    "notification_id": notification["notification_id"]
                },
                token=fcm_token,
            )

            # Send
            response = messaging.send(message_payload)
            print("🔥 FCM Notification Sent:", response)
        else:
            print(f"⚠️ No FCM Token found for user related to student {user_id}")

    except Exception as e:
        print(f"❌ FCM Push Failed: {e}")

    return notification
