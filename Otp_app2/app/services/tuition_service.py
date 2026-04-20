import os
import json
import uuid
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from openai import AsyncOpenAI
import logging
from app.utils.ai_usage_logger import log_ai_usage


logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_syllabus_with_ai(db, student_class: str, subject: str) -> dict:
    """
    Reads textbook chapters for a given class+subject and uses GPT-4o 
    to chunk them into 45-minute logical teaching topics.
    """
    # 1. Fetch Chapters
    cursor = db.textbook_chapters.find({"standard": str(student_class), "subject": subject})
    chapters = await cursor.to_list(length=None)
    
    if not chapters:
        raise ValueError(f"No textbook chapters found for Class {student_class} {subject}")

    # Prepare summary for prompt
    chapter_summary = ""
    for ch in chapters:
        chapter_summary += f"- Chapter: {ch.get('chapter_title', 'Unknown')}\n"
        content_preview = ch.get('content', '')[:300].replace('\n', ' ')
        chapter_summary += f"  Preview: {content_preview}...\n"

    # 2. Call OpenAI
    prompt = f"""
    You are an expert curriculum designer.
    I have the following textbook chapters for Class {student_class} {subject}:
    {chapter_summary}

    TASK:
    Design a COMPLETE, long-term curriculum syllabus by breaking these chapters down into individual "Class Sessions". 
    Each item in the list represents ONE FULL DAY'S TUITION CLASS. 
    There should be as many sessions as necessary to cover all the material. 
    Each class session should take roughly 45 minutes to complete.
    
    OUTPUT FORMAT (JSON strictly):
    {{
      "topics": [
        {{
          "chapter": "Name of the source chapter this topic belongs to",
          "title": "Topic Name (e.g., Session 1: Introduction to the Cell)",
          "description": "Brief description of what will be taught in this specific session",
          "estimated_duration_mins": 45
        }}
      ]
    }}
    """

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)
    
    # Log AI usage
    await log_ai_usage("ADMIN", "generate_syllabus", "gpt-4o-mini", response.usage)
    
    # 3. Add IDs and order
    topics = result.get("topics", [])
    for idx, t in enumerate(topics):
        t["topic_id"] = str(uuid.uuid4())
        t["order_index"] = idx + 1

    # Save to MongoDB
    syllabus_doc = {
        "student_class": student_class,
        "subject": subject,
        "topics": topics,
        "created_at": datetime.now(timezone.utc)
    }

    # Upsert so we don't duplicate
    await db.syllabuses.update_one(
        {"student_class": student_class, "subject": subject},
        {"$set": syllabus_doc},
        upsert=True
    )

    return syllabus_doc


async def map_syllabus_to_timetable(db, student_id: str, student_class: str, subject: str, start_date: datetime):
    """
    Takes the master syllabus and maps the topics sequentially to the user's weekly timetable slots.
    """
    # 1. Fetch User's Timetable Config
    try:
        s_oid = ObjectId(student_id)
    except:
        s_oid = student_id
        
    config = await db.student_timetable_configs.find_one({"student_id": student_id})
    if not config or not config.get("slots"):
        raise ValueError("User has not set up preferred timetable slots.")

    slots = [s for s in config["slots"] if s.get("subject", "").lower() == subject.lower()]
    if not slots:
        raise ValueError(f"No slots reserved for {subject} in the user's timetable.")

    # 2. Fetch Master Syllabus
    syllabus = await db.syllabuses.find_one({"student_class": student_class, "subject": subject})
    if not syllabus:
        raise ValueError("Master syllabus not found. Ensure Admin generates it first.")

    topics = sorted(syllabus.get("topics", []), key=lambda x: x["order_index"])
    
    # 3. Generate future sessions
    days_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    
    current_date = start_date
    created_sessions = []
    
    # Simple allocation: loop through days, if day matches a slot, assign next topic
    topic_idx = 0
    while topic_idx < len(topics):
        day_name = current_date.strftime("%A").lower()
        
        for slot in slots:
            if slot["day_of_week"].lower() == day_name:
                # Assign this topic to this date/time
                time_str = slot["start_time"]
                hour, minute = map(int, time_str.split(':'))
                
                # Create naive datetime from date, then add time, then make aware
                session_time = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                session_doc = {
                    "student_id": ObjectId(student_id),
                    "subject": subject,
                    "topic": topics[topic_idx],
                    "scheduled_time": session_time,
                    "status": "pending",  # pending, active, completed, backlog
                    "session_state": "PENDING", # PENDING -> RECAP -> TEACH -> PRACTICE -> COMPLETED
                    "created_at": datetime.now(timezone.utc)
                }
                
                created_sessions.append(session_doc)
                topic_idx += 1
                if topic_idx >= len(topics):
                    break
        
        current_date += timedelta(days=1)
        
    # Batch insert
    if created_sessions:
        await db.tuition_sessions.insert_many(created_sessions)
        
    return {"message": f"Allocated {len(created_sessions)} sessions."}
