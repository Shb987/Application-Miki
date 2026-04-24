import asyncio
import datetime
import pytz
from app.services.notification_service import broadcast_notification, create_notification
from bson import ObjectId

async def check_and_notify_special_days(db):
    """
    Checks if there is a special day today and sends a broadcast notification.
    """
    # Use IST (Asia/Kolkata) for local consistency
    tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.datetime.now(tz)
    today_str = now_ist.strftime("%Y-%m-%d")
    
    print(f"[Scheduler] Checking for special days on {today_str} (IST)...")
    
    # Only find events that haven't been notified yet today
    special_day = await db.special_days.find_one({
        "date": today_str, 
        "is_active": True,
        "notification_sent": {"$ne": True}
    })
    
    if special_day:
        title = f"Today's {special_day['type']}: {special_day['title']}"
        message = f"Good morning! Today is {special_day['title']}. Activity: {special_day.get('activity') or special_day['description']}"
        
        print(f"[Scheduler] Found event: {special_day['title']}. Sending broadcast...")
        
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
            print(f"[Scheduler] Marked '{special_day['title']}' as notified.")
            
        except Exception as e:
            print(f"[Scheduler] Failed to broadcast: {e}")
    else:
        print(f"[Scheduler] No unsent special day found for {today_str}.")

async def start_special_day_scheduler(db):
    """
    Starts a background loop that checks for special days at 8:00 AM IST.
    """
    print("[Scheduler] Special Day Background Service Started.")
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
            print(f"[Scheduler] Sleeping until {next_run.strftime('%Y-%m-%d %H:%M:%S')} IST...")
            
            await asyncio.sleep(sleep_duration)
            
        except Exception as e:
            print(f"[Scheduler] Error in background loop: {e}")
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
        
        print(f"[Tuition Scheduler] Notifying student {student_id} about upcoming {subject} class...")
        
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
            print(f"[Tuition Scheduler] Marked session {session['_id']} as notified.")
            
        except Exception as e:
            print(f"[Tuition Scheduler] Failed to notify student {student_id}: {e}")

async def check_and_handle_missed_sessions(db):
    """
    Finds sessions that were never started and are now more than 30 mins late.
    Marks them as absent and triggers a re-map to shift the topic forward.
    """
    # Lazy import to avoid circular dependency
    from app.services.tuition_service import map_syllabus_to_timetable
    
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    threshold_dt = now_utc - datetime.timedelta(minutes=30)
    
    # Identify pending sessions that passed the grace period
    query = {
        "status": "pending",
        "scheduled_time": {"$lt": threshold_dt.replace(tzinfo=None)}
    }
    
    cursor = db.tuition_sessions.find(query)
    missed_sessions = await cursor.to_list(length=None)
    
    if missed_sessions:
        print(f"[Tuition Scheduler] Found {len(missed_sessions)} missed sessions. Marking as absent...")

    remap_targets = set()
    
    for session in missed_sessions:
        s_id = str(session["student_id"])
        subj = session["subject"]
        
        try:
            # 1. Mark as absent
            await db.tuition_sessions.update_one(
                {"_id": session["_id"]},
                {"$set": {"status": "absent", "attendance": "absent"}}
            )
            remap_targets.add((s_id, subj))
        except Exception as e:
            print(f"[Tuition Scheduler] Error handling absence for session {session['_id']}: {e}")

    # 2. Re-map curriculum for affected students
    for s_id, subj in remap_targets:
        try:
            student = await db.students.find_one({"_id": ObjectId(s_id)})
            student_class = str(student.get("student_class", "8")) if student else "8"
            
            # Clear remaining future 'pending' sessions for this specific subject
            await db.tuition_sessions.delete_many({
                "student_id": ObjectId(s_id),
                "subject": subj,
                "status": "pending"
            })
            
            # Shift the curriculum to start from tomorrow
            tomorrow = now_utc + datetime.timedelta(days=1)
            await map_syllabus_to_timetable(db, s_id, student_class, subj, tomorrow)
            print(f"[Tuition Scheduler] Shifted curriculum for Student {s_id}, Subject: {subj}")
            
        except Exception as e:
            print(f"[Tuition Scheduler] Failed to re-map for {s_id}: {e}")

async def start_tuition_scheduler(db):
    """
    Starts a background loop that checks for reminders and missed classes.
    """
    print("[Tuition Scheduler] Background Service Started.")
    
    while True:
        try:
            # 1. Reminders (Upcoming)
            await check_and_notify_upcoming_tuition(db)
            
            # 2. Clean-up (Missed/Absent)
            await check_and_handle_missed_sessions(db)
            
        except Exception as e:
            print(f"[Tuition Scheduler] Error in background loop: {e}")
            
        # Sleep for 60 seconds before checking again
        await asyncio.sleep(60)
