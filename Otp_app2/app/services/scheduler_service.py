import asyncio
import datetime
import pytz
from app.services.notification_service import broadcast_notification

async def check_and_notify_special_days(db):
    """
    Checks if there is a special day today and sends a broadcast notification.
    """
    # Use IST or your server's local time as per project convention
    # For now using UTC but formatting to YYYY-MM-DD
    today_str = datetime.datetime.now(pytz.UTC).strftime("%Y-%m-%d")
    
    print(f"⏰ [Scheduler] Checking for special days on {today_str}...")
    
    special_day = await db.special_days.find_one({"date": today_str, "is_active": True})
    
    if special_day:
        title = f"Today's {special_day['type']}: {special_day['title']}"
        message = f"Good morning! Today is {special_day['title']}. Activity: {special_day.get('activity') or special_day['description']}"
        
        print(f"📢 [Scheduler] Found event: {special_day['title']}. Sending broadcast...")
        
        await broadcast_notification(
            db=db,
            title=title,
            message=message,
            notification_type="special_day_reminder",
            extra_data={"date": today_str, "type": special_day['type']}
        )
    else:
        print("ℹ️ [Scheduler] No special day found for today.")

async def start_special_day_scheduler(db):
    """
    Starts a background loop that checks for special days once a day.
    """
    print("🚀 [Scheduler] Special Day Background Service Started.")
    
    while True:
        try:
            # Run the check
            await check_and_notify_special_days(db)
            
            # Wait for 24 hours (86400 seconds)
            # Alternatively, calculate time until 8:00 AM next day
            # for now, simple 24h loop for demonstration/simplicity
            # In production, you'd calculate: (next_8am - now).total_seconds()
            
            now = datetime.datetime.now(pytz.UTC)
            # Target 8:00 AM UTC (adjust to IST if needed)
            next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += datetime.timedelta(days=1)
            
            sleep_duration = (next_run - now).total_seconds()
            print(f"💤 [Scheduler] Sleeping for {sleep_duration/3600:.2f} hours until {next_run}...")
            
            await asyncio.sleep(sleep_duration)
            
        except Exception as e:
            print(f"❌ [Scheduler] Error in background loop: {e}")
            await asyncio.sleep(60) # Retry after 1 minute on error
