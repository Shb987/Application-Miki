import asyncio
import datetime
import pytz
from app.services.notification_service import broadcast_notification, create_notification

async def check_and_notify_special_days(db):
    """
    Checks if there is a special day today and sends a broadcast notification.
    """
    # Use IST (Asia/Kolkata) for local consistency
    tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.datetime.now(tz)
    today_str = now_ist.strftime("%Y-%m-%d")
    
    print(f"⏰ [Scheduler] Checking for special days on {today_str} (IST)...")
    
    # Only find events that haven't been notified yet today
    special_day = await db.special_days.find_one({
        "date": today_str, 
        "is_active": True,
        "notification_sent": {"$ne": True}
    })
    
    if special_day:
        title = f"Today's {special_day['type']}: {special_day['title']}"
        message = f"Good morning! Today is {special_day['title']}. Activity: {special_day.get('activity') or special_day['description']}"
        
        print(f"📢 [Scheduler] Found event: {special_day['title']}. Sending broadcast...")
        
        try:
            await broadcast_notification(
                db=db,
                title=title,
                message=message,
                notification_type="special_day_reminder",
                extra_data={"date": today_str, "type": special_day['type']},
                priority=5
            )
            
            # Mark as sent
            await db.special_days.update_one(
                {"_id": special_day["_id"]},
                {"$set": {"notification_sent": True}}
            )
            print(f"✅ [Scheduler] Marked '{special_day['title']}' as notified.")
            
        except Exception as e:
            print(f"❌ [Scheduler] Failed to broadcast: {e}")
    else:
        print(f"ℹ️ [Scheduler] No unsent special day found for {today_str}.")

async def start_special_day_scheduler(db):
    """
    Starts a background loop that checks for special days at 8:00 AM IST.
    """
    print("🚀 [Scheduler] Special Day Background Service Started.")
    tz = pytz.timezone("Asia/Kolkata")
    
    while True:
        try:
            await check_and_notify_special_days(db)
            
            now = datetime.datetime.now(tz)
            # Target 8:00 AM IST
            next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
            
            if next_run <= now:
                next_run += datetime.timedelta(days=1)
            
            sleep_duration = (next_run - now).total_seconds()
            print(f"💤 [Scheduler] Sleeping until {next_run.strftime('%Y-%m-%d %H:%M:%S')} IST...")
            
            await asyncio.sleep(sleep_duration)
            
        except Exception as e:
            print(f"❌ [Scheduler] Error in background loop: {e}")
            await asyncio.sleep(60)

async def check_and_notify_upcoming_tuition(db):
    """
    Checks for tuition sessions starting within the next 15 minutes and sends targeted notifications.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    # 15 minutes from now
    target_time = now_utc + datetime.timedelta(minutes=15)
    
    # Query: status is pending, not yet notified, and scheduled_time is in the past OR up to 15 mins from now
    query = {
        "status": "pending",
        "notification_sent": {"$ne": True},
        "scheduled_time": {"$lte": target_time}
    }
    
    cursor = db.tuition_sessions.find(query)
    sessions = await cursor.to_list(length=None)
    
    for session in sessions:
        student_id = str(session["student_id"])
        subject = session.get("subject", "Class")
        topic_title = session.get("topic", {}).get("title", "Unknown Topic")
        
        title = f"Your {subject} class starts soon!"
        message = f"Get ready! Your session on '{topic_title}' is about to begin. Open the app to join."
        
        print(f"📢 [Tuition Scheduler] Notifying student {student_id} about upcoming {subject} class...")
        
        try:
            await create_notification(
                db=db,
                user_id=student_id,
                title=title,
                message=message,
                notification_type="tuition_class_reminder",
                extra_data={
                    "session_id": str(session["_id"]),
                    "subject": subject
                },
                priority=10  # High priority push
            )
            
            # Mark as notified
            await db.tuition_sessions.update_one(
                {"_id": session["_id"]},
                {"$set": {"notification_sent": True}}
            )
            print(f"✅ [Tuition Scheduler] Marked session {session['_id']} as notified.")
            
        except Exception as e:
            print(f"❌ [Tuition Scheduler] Failed to notify student {student_id}: {e}")

async def start_tuition_scheduler(db):
    """
    Starts a background loop that checks for upcoming tuition classes every 60 seconds.
    """
    print("🚀 [Tuition Scheduler] Background Service Started.")
    
    while True:
        try:
            await check_and_notify_upcoming_tuition(db)
        except Exception as e:
            print(f"❌ [Tuition Scheduler] Error in background loop: {e}")
            
        # Sleep for 60 seconds before checking again
        await asyncio.sleep(60)
