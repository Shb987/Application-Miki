import os
import json
import uuid
import re
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
import pytz
from bson import ObjectId
from openai import AsyncOpenAI
import logging
from app.utils.ai_usage_logger import log_ai_usage


logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or "sk-placeholder")

TUITION_AUDIO_DIR = os.path.join("app", "static", "uploads", "tuition_audio")
os.makedirs(TUITION_AUDIO_DIR, exist_ok=True)


async def generate_tuition_speech(
    text: str,
    session_id: Optional[str] = None,
    voice: str = "nova"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Synthesizes natural, human-like voice speech for Miki using OpenAI TTS.
    Saves an MP3 file to app/static/uploads/tuition_audio/ and returns (audio_url, audio_base64).
    Gracefully returns (None, None) if TTS synthesis is unavailable or fails.
    """
    if not text or not text.strip():
        return None, None

    # Clean text: remove internal state transitions, bracketed tokens, and excessive markdown
    clean_text = re.sub(r'\[SYSTEM_CHANGE_STATE:[^\]]+\]', '', text).strip()
    clean_text = re.sub(r'[*_#`]', '', clean_text).strip()
    if not clean_text:
        return None, None

    valid_voices = {"nova", "alloy", "echo", "fable", "onyx", "shimmer"}
    chosen_voice = voice.lower() if voice and voice.lower() in valid_voices else "nova"

    try:
        tts_res = await client.audio.speech.create(
            model="tts-1",
            voice=chosen_voice,
            input=clean_text[:4096],
            response_format="mp3"
        )
        audio_bytes = tts_res.content
        if not audio_bytes:
            return None, None

        audio_id = f"miki_{session_id or 'tuition'}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
        audio_filename = f"{audio_id}.mp3"
        audio_filepath = os.path.join(TUITION_AUDIO_DIR, audio_filename)

        with open(audio_filepath, "wb") as f:
            f.write(audio_bytes)

        audio_url = f"/uploads/tuition_audio/{audio_filename}"
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        return audio_url, audio_base64
    except Exception as e:
        logger.warning(f"[Tuition-TTS] Failed to generate Miki voice speech: {e}")
        return None, None


async def delete_session_audio(session_id: str, db=None) -> int:
    """
    Deletes all temporary Miki speech audio files generated for a specific tuition session.
    """
    if not session_id:
        return 0
    deleted_count = 0
    pattern = f"miki_{session_id}_"
    try:
        if os.path.exists(TUITION_AUDIO_DIR):
            for fname in os.listdir(TUITION_AUDIO_DIR):
                if fname.startswith(pattern) and fname.endswith(".mp3"):
                    fpath = os.path.join(TUITION_AUDIO_DIR, fname)
                    try:
                        os.remove(fpath)
                        deleted_count += 1
                    except Exception as err:
                        logger.warning(f"[Tuition-Audio] Could not remove {fpath}: {err}")
        if db is not None:
            try:
                s_oid = ObjectId(session_id)
                await db.tuition_chat_logs.update_many(
                    {"session_id": s_oid},
                    {"$unset": {"audio_url": ""}}
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[Tuition-Audio] Error cleaning audio for session {session_id}: {e}")
    return deleted_count


async def auto_cleanup_tuition_audio(
    db=None,
    max_age_hours: float = 2.0,
    completed_grace_mins: int = 15
) -> int:
    """
    Automatically purges temporary Miki tuition speech files:
    1. Audio files older than max_age_hours (default: 2 hours).
    2. Audio files from completed or absent sessions after completed_grace_mins (default: 15 mins)
       giving the student ample time to listen to the final summary.
    """
    if not os.path.exists(TUITION_AUDIO_DIR):
        return 0

    now_ts = datetime.now().timestamp()
    deleted_count = 0
    max_age_secs = max_age_hours * 3600
    grace_secs = completed_grace_mins * 60

    try:
        filenames = [f for f in os.listdir(TUITION_AUDIO_DIR) if f.endswith(".mp3")]
        if not filenames:
            return 0

        # Query completed/absent session IDs to match files
        completed_session_ids = set()
        if db is not None:
            try:
                done_sessions = await db.tuition_sessions.find(
                    {"status": {"$in": ["completed", "absent"]}},
                    {"_id": 1}
                ).to_list(1000)
                completed_session_ids = {str(s["_id"]) for s in done_sessions}
            except Exception as e:
                logger.warning(f"[Tuition-Audio] Failed to query completed sessions: {e}")

        for fname in filenames:
            fpath = os.path.join(TUITION_AUDIO_DIR, fname)
            try:
                stat = os.stat(fpath)
                file_age_secs = now_ts - stat.st_mtime

                should_delete = False

                if file_age_secs >= max_age_secs:
                    should_delete = True
                else:
                    parts = fname.replace(".mp3", "").split("_")
                    if len(parts) >= 2 and parts[0] == "miki":
                        sess_id = parts[1]
                        if sess_id in completed_session_ids and file_age_secs >= grace_secs:
                            should_delete = True

                if should_delete:
                    os.remove(fpath)
                    deleted_count += 1
            except Exception as fe:
                logger.warning(f"[Tuition-Audio] Could not remove {fpath}: {fe}")

        if deleted_count > 0:
            print(f"[Tuition-Audio] Automatically cleaned up {deleted_count} expired Miki tuition audio files.")
    except Exception as e:
        logger.warning(f"[Tuition-Audio] Error during automatic audio cleanup: {e}")

    return deleted_count

async def generate_syllabus_with_ai(db, student_class: str, subject: str, board: str = "State") -> dict:
    """
    Reads textbook chapters for a given class+subject+board and uses GPT-4o 
    to chunk them into 45-minute logical teaching topics.
    """
    # Normalize board string: State vs CBSE
    raw_board = str(board).strip() if board else "State"
    if raw_board.upper() in ["CBSE", "NCERT"]:
        norm_board = "CBSE"
    elif raw_board.upper() in ["STATE", "SCERT"]:
        norm_board = "State"
    else:
        norm_board = raw_board

    # 1. Fetch Chapters with board filter
    chapter_query = {"standard": str(student_class), "subject": subject}
    if norm_board.lower() in ["state", "scert"]:
        chapter_query["board"] = {"$regex": "^(State|SCERT|Kerala)$", "$options": "i"}
    elif norm_board.lower() in ["cbse", "ncert"]:
        chapter_query["board"] = {"$regex": "^(CBSE|NCERT)$", "$options": "i"}
    elif norm_board:
        chapter_query["board"] = {"$regex": f"^{re.escape(norm_board)}$", "$options": "i"}

    cursor = db.textbook_chapters.find(chapter_query)
    chapters = await cursor.to_list(length=None)
    
    # If not found with specific board regex, try general standard + subject
    if not chapters:
        chapters = await db.textbook_chapters.find({"standard": str(student_class), "subject": subject}).to_list(length=None)

    if not chapters:
        raise ValueError(f"No textbook chapters found for Class {student_class} {subject} ({norm_board} Board)")

    # Prepare summary for prompt
    chapter_summary = ""
    for ch in chapters:
        chapter_summary += f"- Chapter: {ch.get('chapter_title', 'Unknown')}\n"
        content_preview = ch.get('content', '')[:300].replace('\n', ' ')
        chapter_summary += f"  Preview: {content_preview}...\n"

    # 2. Call OpenAI
    prompt = f"""
    You are an expert curriculum designer.
    I have the following textbook chapters for Class {student_class} {subject} ({norm_board} Curriculum):
    {chapter_summary}

    TASK:
    Design a COMPLETE, long-term curriculum syllabus by breaking these chapters down into individual "Class Sessions" adhering to {norm_board} standards. 
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
        "student_class": str(student_class),
        "subject": subject,
        "board": norm_board,
        "topics": topics,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }

    # Upsert with board so State and CBSE can coexist
    await db.syllabuses.update_one(
        {"student_class": str(student_class), "subject": subject, "board": norm_board},
        {"$set": syllabus_doc},
        upsert=True
    )

    return syllabus_doc


async def map_syllabus_to_timetable(db, student_id: str, student_class: str, subject: str, start_date: datetime):
    """
    Takes the master syllabus and maps the remaining (uncompleted) topics 
    sequentially to the user's weekly timetable slots.
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

    # 2. Fetch Master Syllabus & Filter out Completed Topics
    # Support student's preferred board if set
    student_doc = None
    try:
        student_doc = await db.students.find_one({"_id": s_oid})
    except:
        pass
    
    board_pref = student_doc.get("board") or student_doc.get("syllabus") if student_doc else None
    syl_query = {"student_class": str(student_class), "subject": subject}
    if board_pref:
        if str(board_pref).lower() in ["state", "scert"]:
            syl_query["board"] = {"$regex": "^(State|SCERT)$", "$options": "i"}
        elif str(board_pref).lower() in ["cbse", "ncert"]:
            syl_query["board"] = {"$regex": "^(CBSE|NCERT)$", "$options": "i"}
    
    syllabus = await db.syllabuses.find_one(syl_query)
    if not syllabus:
        syllabus = await db.syllabuses.find_one({"student_class": str(student_class), "subject": subject})
    if not syllabus:
        raise ValueError(f"Master syllabus not found for Class {student_class} {subject}. Ensure Admin generates it first.")

    all_topics = sorted(syllabus.get("topics", []), key=lambda x: x["order_index"])
    
    # NEW: Find which topics are already completed
    completed_sessions = await db.tuition_sessions.find({
        "student_id": ObjectId(student_id),
        "subject": subject,
        "status": "completed"
    }).to_list(None)
    
    completed_topic_ids = {str(s["topic"]["topic_id"]) for s in completed_sessions if s.get("topic")}
    
    # Filter syllabus to only include uncompleted topics
    topics_to_map = [t for t in all_topics if str(t["topic_id"]) not in completed_topic_ids]

    if not topics_to_map:
        return {"message": "All topics for this subject are already completed."}

    # 3. Generate future sessions
    tz = pytz.timezone("Asia/Kolkata")
    current_date = start_date.astimezone(tz)
    created_sessions = []
    
    topic_idx = 0
    # Guard against infinite loops if no slots match
    max_days = 365 
    days_checked = 0

    while topic_idx < len(topics_to_map) and days_checked < max_days:
        day_name = current_date.strftime("%A").lower()
        
        # Check all slots for this day
        for slot in slots:
            if slot["day_of_week"].lower() == day_name:
                time_str = slot["start_time"] # e.g. "18:00"
                hour, minute = map(int, time_str.split(':'))
                
                # 4. Correct Timezone Handling (IST -> UTC)
                # Set target time in IST
                session_time_ist = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # If this time has already passed today, skip to next occurrence
                if session_time_ist < start_date.astimezone(tz):
                    continue
                
                # Convert back to UTC for database storage
                session_time_utc = session_time_ist.astimezone(pytz.UTC).replace(tzinfo=None)
                
                session_doc = {
                    "student_id": ObjectId(student_id),
                    "subject": subject,
                    "topic": topics_to_map[topic_idx],
                    "scheduled_time": session_time_utc,
                    "status": "pending",
                    "attendance": "pending",
                    "session_state": "PENDING",
                    "created_at": datetime.now(timezone.utc)
                }
                
                created_sessions.append(session_doc)
                topic_idx += 1
                if topic_idx >= len(topics_to_map):
                    break
        
        current_date += timedelta(days=1)
        days_checked += 1
        
    # Batch insert
    if created_sessions:
        await db.tuition_sessions.insert_many(created_sessions)
        
    return {"message": f"Allocated {len(created_sessions)} future sessions."}
