from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Dict, Any
from datetime import datetime, timezone
from app.core.database import db
from app.utils.user_auth import get_current_user, admin_or_user
from app.utils.admin_auth import get_current_admin
from app.services.tuition_service import generate_syllabus_with_ai, map_syllabus_to_timetable
from app.models.tuition_models import StudentTimetableConfig, TuitionChatRequest
from app.utils.ai_usage_logger import log_ai_usage
from pydantic import BaseModel
from bson import ObjectId
import os
from openai import AsyncOpenAI
from app.utils.usage_guard import check_and_use_quota, has_premium_access

async def check_premium(student_id: str):
    if not await has_premium_access(student_id):
        raise HTTPException(status_code=403, detail="Digital Tuition is a Premium feature. Please upgrade to Plus or Pro.")

router = APIRouter(tags=["Digital Tuition"])
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def serialize_mongo(doc):
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, dict):
        return {k: serialize_mongo(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [serialize_mongo(i) for i in doc]
    if isinstance(doc, datetime):
        return doc.isoformat() + "Z" if not doc.tzinfo else doc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return doc

# ----------------- ADMIN ----------------- #

@router.post("/admin/tuition/generate-syllabus")
async def admin_generate_syllabus(
    student_class: str = Body(...), 
    subject: str = Body(...),
    admin=Depends(get_current_admin)
):
    try:
        result = await generate_syllabus_with_ai(db, student_class, subject)
        return {"status_code": 200, "message": "Syllabus generated successfully", "data": serialize_mongo(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/tuition/syllabuses")
async def get_syllabuses(student_class: str = None, subject: str = None, admin=Depends(get_current_admin)):
    query = {}
    if student_class: query["student_class"] = student_class
    if subject: query["subject"] = subject
    
    docs = await db.syllabuses.find(query).to_list(None)
    return {"status_code": 200, "data": serialize_mongo(docs)}

@router.put("/admin/tuition/syllabus/{syllabus_id}")
async def admin_edit_syllabus(
    syllabus_id: str,
    topics: list = Body(...),
    admin=Depends(get_current_admin)
):
    try:
        s_oid = ObjectId(syllabus_id)
        # Ensure order_index is updated properly format
        for idx, t in enumerate(topics):
            t["order_index"] = idx + 1
            
        result = await db.syllabuses.update_one(
            {"_id": s_oid},
            {"$set": {"topics": topics, "updated_at": datetime.now(timezone.utc)}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Syllabus not found")
            
        return {"status_code": 200, "message": "Syllabus updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------- USER / PARENT ----------------- #

@router.post("/user/tuition/setup-timetable")
async def setup_timetable(
    config: StudentTimetableConfig, 
    current_user: dict = Depends(admin_or_user)
):
    """
    Parent slots setter. Strictly appends new slots (e.g., adding a subject on a different day) 
    without replacing/overwriting any existing slots unless they are exact duplicates.
    """
    await check_premium(config.student_id)
    subjects_in_request = list(set([slot.subject for slot in config.slots]))
    
    # 1. Fetch Existing Config & Append
    existing_config = await db.student_timetable_configs.find_one({"student_id": config.student_id})
    final_slots = []
    
    if existing_config and "slots" in existing_config:
        final_slots = existing_config["slots"]
                
    # Append the new slots being submitted now (deduplicating exact matches)
    for new_slot in config.slots:
        ns_dict = new_slot.dict()
        if ns_dict not in final_slots:
            final_slots.append(ns_dict)

    # Save the strictly appended config
    await db.student_timetable_configs.update_one(
        {"student_id": config.student_id},
        {"$set": {
            "student_id": config.student_id,
            "slots": final_slots,
            "updated_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    
    # 2. Re-map future sessions based ONLY on the updated subjects
    try:
        s_oid = ObjectId(config.student_id)
        student = await db.students.find_one({"_id": s_oid})
        student_class = str(student.get("student_class", "8")) if student else "8"
    except:
        student_class = "8"

    results = {}
    for subj in subjects_in_request:
        try:
            # Drop future 'pending' sessions ONLY for this specific subject being updated
            await db.tuition_sessions.delete_many({
                "student_id": ObjectId(config.student_id),
                "subject": subj,
                "status": "pending"
            })
            
            res = await map_syllabus_to_timetable(
                db, 
                config.student_id, 
                student_class, 
                subj, 
                start_date=datetime.now(timezone.utc)
            )
            results[subj] = res["message"]
        except Exception as e:
            results[subj] = f"Error: {str(e)}"
            
    return {"status_code": 200, "message": "Timetable updated selectively", "allocation_results": results}

@router.delete("/user/tuition/subject/{subject_name}")
async def remove_subject_from_timetable(
    subject_name: str,
    student_id: str,
    current_user: dict = Depends(admin_or_user)
):
    """Safely removes a subject from the student's timetable and deletes its uncompleted sessions."""
    await check_premium(student_id)
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    # 1. Remove from base config slots
    existing_config = await db.student_timetable_configs.find_one({"student_id": student_id})
    if existing_config and "slots" in existing_config:
        kept_slots = [s for s in existing_config["slots"] if s.get("subject") != subject_name]
        await db.student_timetable_configs.update_one(
            {"student_id": student_id},
            {"$set": {"slots": kept_slots, "updated_at": datetime.now(timezone.utc)}}
        )
        
    # 2. Delete all pending future sessions
    deleted = await db.tuition_sessions.delete_many({
        "student_id": s_oid,
        "subject": subject_name,
        "status": "pending"
    })
    
    return {"status_code": 200, "message": f"Successfully removed {subject_name}. {deleted.deleted_count} future sessions canceled."}


@router.delete("/user/tuition/slot")
async def remove_specific_slot(
    student_id: str,
    subject: str,
    day_of_week: str,
    start_time: str,
    current_user: dict = Depends(admin_or_user)
):
    """Deletes a specific day/time slot for a subject, and remaps the remaining future sessions."""
    await check_premium(student_id)
    existing_config = await db.student_timetable_configs.find_one({"student_id": student_id})
    if not existing_config or "slots" not in existing_config:
        raise HTTPException(status_code=404, detail="No configuration found")
        
    original_slots = existing_config["slots"]
    # Filter out the exact match
    kept_slots = [
        s for s in original_slots 
        if not (s.get("subject") == subject and str(s.get("day_of_week")).lower() == day_of_week.lower() and s.get("start_time") == start_time)
    ]
    
    if len(kept_slots) == len(original_slots):
        raise HTTPException(status_code=404, detail="Exact slot not found in configuration")

    # Save
    await db.student_timetable_configs.update_one(
        {"student_id": student_id},
        {"$set": {"slots": kept_slots, "updated_at": datetime.now(timezone.utc)}}
    )
    
    # Remap the subject now that it has one less weekly slot
    await db.tuition_sessions.delete_many({
        "student_id": ObjectId(student_id),
        "subject": subject,
        "status": "pending"
    })
    
    try:
        s_oid = ObjectId(student_id)
        student = await db.students.find_one({"_id": s_oid})
        student_class = str(student.get("student_class", "8")) if student else "8"
    except:
        student_class = "8"
        
    await map_syllabus_to_timetable(db, student_id, student_class, subject, datetime.now(timezone.utc))
    return {"status_code": 200, "message": f"Successfully removed {day_of_week} {start_time} slot for {subject} and remapped schedule."}


@router.get("/user/tuition/timetable-config/{student_id}")
async def get_timetable_config(student_id: str, current_user: dict = Depends(admin_or_user)):
    """Fetch the raw slot configuration for a student to pre-fill the frontend scheduler UI."""
    await check_premium(student_id)
    doc = await db.student_timetable_configs.find_one({"student_id": student_id})
    if not doc:
        return {"status_code": 200, "data": []}
    return {"status_code": 200, "data": doc.get("slots", [])}


@router.get("/user/tuition/schedule/{student_id}")
async def get_student_schedule(student_id: str, current_user: dict = Depends(admin_or_user)):
    """Fetch user's allocated class sessions (the schedule loop)."""
    await check_premium(student_id)
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    sessions = await db.tuition_sessions.find({"student_id": s_oid}).sort("scheduled_time", 1).to_list(None)
    return {"status_code": 200, "data": serialize_mongo(sessions)}

@router.get("/user/tuition/available-subjects/{student_class}")
async def get_available_subjects_by_class(student_class: str, current_user: dict = Depends(admin_or_user)):
    """Fetch the list of distinct subjects that have a generated syllabus for a specific class."""
    subjects = await db.syllabuses.distinct("subject", {"student_class": str(student_class)})
    return {"status_code": 200, "data": subjects}


# ----------------- SESSION STATE MACHINE (CLASS MODE) ----------------- #

class PostponeRequest(BaseModel):
    session_id: str

@router.post("/user/tuition/session/postpone")
async def postpone_session(payload: PostponeRequest, current_user: dict = Depends(admin_or_user)):
    """
    If a student is sick/misses a session, postpone it. 
    This gracefully clears the current session and pushes the entire remaining timeline 
    forward starting from tomorrow.
    """
    try:
        s_oid = ObjectId(payload.session_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid session_id")
        
    session = await db.tuition_sessions.find_one({"_id": s_oid})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if session.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Cannot postpone a completed session")

    subject = session.get("subject")
    student_id = str(session.get("student_id"))
    
    # 1. Delete all uncompleted future/pending sessions for this subject
    # This also deletes the specific session they are postponing
    await db.tuition_sessions.delete_many({
        "student_id": ObjectId(student_id),
        "subject": subject,
        "status": {"$ne": "completed"}
    })
    
    # 2. Trigger the dynamic mapper but tell it to START FROM TOMORROW
    try:
        student = await db.students.find_one({"_id": ObjectId(student_id)})
        student_class = str(student.get("student_class", "8")) if student else "8"
    except:
        student_class = "8"
        
    from datetime import timedelta
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    
    await map_syllabus_to_timetable(db, student_id, student_class, subject, tomorrow)
    
    return {"status_code": 200, "message": "Session successfully postponed. Future schedule dynamically adjusted."}

@router.post("/user/tuition/session/start")
async def start_session(session_id: str = Body(...), current_user: dict = Depends(admin_or_user)):
    """Marks a scheduled session as 'active' and starts the RECAP state with time validation."""
    try:
        s_oid = ObjectId(session_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid session_id")
        
    session = await db.tuition_sessions.find_one({"_id": s_oid})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Pre-checks
    if session.get("status") == "completed":
        return {"status_code": 400, "can_join": False, "message": "This session is already completed."}
    if session.get("status") == "absent":
        return {"status_code": 400, "can_join": False, "message": "You were marked absent for this session."}

    # 1. Time Window Validation (-15m to +30m)
    now = datetime.now(timezone.utc)
    scheduled_time = session.get("scheduled_time")
    
    if scheduled_time.tzinfo is None:
        scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        
    diff_mins = (now - scheduled_time).total_seconds() / 60
    
    # Use boolean logic as requested
    is_too_early = diff_mins < -15
    is_too_late = diff_mins > 30
    can_join = not is_too_early and not is_too_late
    
    if is_too_early:
        return {
            "status_code": 403, 
            "can_join": False,
            "message": f"Too early. Please join within 15 minutes of the start time ({scheduled_time.strftime('%H:%M')} UTC)."
        }
    
    if is_too_late:
        # Mark as absent if they missed the window
        if session.get("status") != "absent":
            await db.tuition_sessions.update_one(
                {"_id": s_oid},
                {"$set": {"status": "absent", "attendance": "absent"}}
            )
        return {
            "status_code": 403, 
            "can_join": False,
            "message": "Too late. You have been marked absent for this session."
        }

    # 2. Mark as Active and Present
    if can_join:
        # 🚨 Check & Use Quota (1 class session)
        student_id_str = str(session.get("student_id"))
        await check_and_use_quota(student_id_str, "class", cost=1)

        await db.tuition_sessions.update_one(
            {"_id": s_oid},
            {"$set": {
                "status": "active", 
                "attendance": "present",
                "session_state": "RECAP",
                "started_at": now
            }}
        )
        
        topic = session.get("topic", {})
        return {
            "status_code": 200,
            "can_join": True,
            "message": "Class started",
            "initial_tutor_message": f"Welcome to today's class on {topic.get('title')}! Let's start with a quick recap. Are you ready?"
        }
    
    return {"status_code": 500, "can_join": False, "message": "Unknown error starting session."}


@router.post("/user/tuition/session/chat")
async def tuition_session_chat(
    payload: TuitionChatRequest, 
    current_user: dict = Depends(admin_or_user)
):
    """
    The strictly structured AI Tutor chat for active class mode.
    """
    try:
        session_oid = ObjectId(payload.session_id)
        student_oid = ObjectId(payload.student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid IDs")

    session = await db.tuition_sessions.find_one({"_id": session_oid})
    if not session or session.get("status") != "active":
        raise HTTPException(status_code=400, detail="Session is not active.")

    state = session.get("session_state", "RECAP")
    topic = session.get("topic", {})
    title = topic.get("title", "Unknown")
    desc = topic.get("description", "")
    chapter_name = topic.get("chapter")
    
    # 1. Fetch Student for Class details
    student = await db.students.find_one({"_id": student_oid})
    student_class = str(student.get("student_class", "8")) if student else "8"
    subject = session.get("subject", "")
    
    # 2. Fetch specific textbook chapter content to constrain the AI
    source_material = ""
    if state in ["TEACH", "PRACTICE"] and chapter_name:
        chapter_doc = await db.textbook_chapters.find_one({
            "standard": student_class,
            "subject": subject,
            "chapter_title": chapter_name
        })
        if chapter_doc and "content" in chapter_doc:
            source_material = f"\n\nSOURCE REFERENCE MATERIAL (TEACH ONLY FROM THIS):\n{chapter_doc['content'][:25000]}"
    
    # State-specific System Prompts to enforce discipline
    state_instructions = {
        "RECAP": "Your goal is to test the student's prior knowledge or general readiness for the topic. Ask 1-2 engaging questions. If they answer reasonably well, explicitly state '[SYSTEM_CHANGE_STATE: TEACH]' at the end of your message to move on.",
        "TEACH": f"Your goal is to teach the topic: '{title}'. Description: {desc}. Teach it step-by-step in an engaging way. YOU MUST STRICTLY USE THE FACTS AND CONCEPTS FROM THE SOURCE REFERENCE MATERIAL PROVIDED BELOW. Do not invent outside concepts. Once you have explained the core concept clearly, explicitly state '[SYSTEM_CHANGE_STATE: PRACTICE]' to move on.",
        "PRACTICE": "Your goal is to test the student on what you just taught. Ask them to solve a problem or answer a specific question about the topic derived directly from the Source Reference Material. If they get it right, explicitly state '[SYSTEM_CHANGE_STATE: SUMMARY]' to conclude.",
        "SUMMARY": "Provide a brief summary of the class, praise the student, and assign 1 small homework task. Then clearly state 'Class Dismissed'."
    }
    
    system_instruction = state_instructions.get(state, state_instructions["RECAP"])
    
    # Time Awareness Logic
    now = datetime.now(timezone.utc)
    started_at = session.get("started_at")
    if started_at:
        # Normalize timezone
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        elapsed_mins = int((now - started_at).total_seconds() / 60)
    else:
        # Fallback if started_at is missing
        elapsed_mins = 0

    time_status = f"Class duration so far: {elapsed_mins} minutes."
    time_instruction = ""
    
    if elapsed_mins >= 55:
        time_instruction = "IMPORTANT: You have reached the maximum 1-hour limit. Regardless of whether the topic is finished, you MUST conclude the class NOW. Move to SUMMARY phase immediately and end with 'Class Dismissed'."
    elif elapsed_mins >= 40:
        time_instruction = "NOTE: You are approaching the 45-minute lesson target. Start winding up the current phase and move towards the SUMMARY phase soon to keep the schedule."

    prompt = f"""
    You are 'Miki', an expert Digital Institute Tutor leading a live, structured class.
    
    CURRENT PHASE: {state}
    TOPIC TODAY: {title}
    TIME STATUS: {time_status}
    {time_instruction}
    
    CRITICAL RULE FOR DISCIPLINE: 
    If the student asks a random off-topic question, firmly but politely redirect them back to the current phase of the lesson. Do not satisfy off-topic tangents during Class Mode.
    
    INSTRUCTIONS FOR THIS PHASE:
    {system_instruction}
    {source_material}
    """

    # Fetch simple history for this session specifically
    history_docs = await db.tuition_chat_logs.find({"session_id": session_oid}).sort("_id", 1).to_list(10)
    messages = [{"role": "system", "content": prompt}]
    for doc in history_docs:
        messages.append({"role": doc["role"], "content": doc["content"]})
        
    # Append new user message
    messages.append({"role": "user", "content": payload.message})

    # Call AI
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.5
    )
    
    ai_reply = response.choices[0].message.content
    
    # Log AI Usage
    await log_ai_usage(str(student_oid), "tuition_session_chat", "gpt-4o", response.usage)
    
    # Handle State Transitions
    new_state = state
    if "[SYSTEM_CHANGE_STATE: TEACH]" in ai_reply:
        new_state = "TEACH"
        ai_reply = ai_reply.replace("[SYSTEM_CHANGE_STATE: TEACH]", "").strip()
    elif "[SYSTEM_CHANGE_STATE: PRACTICE]" in ai_reply:
        new_state = "PRACTICE"
        ai_reply = ai_reply.replace("[SYSTEM_CHANGE_STATE: PRACTICE]", "").strip()
    elif "[SYSTEM_CHANGE_STATE: SUMMARY]" in ai_reply:
        new_state = "SUMMARY"
        ai_reply = ai_reply.replace("[SYSTEM_CHANGE_STATE: SUMMARY]", "").strip()

    # Save to logs
    await db.tuition_chat_logs.insert_many([
        {"session_id": session_oid, "student_id": student_oid, "role": "user", "content": payload.message, "created_at": datetime.now(timezone.utc)},
        {"session_id": session_oid, "student_id": student_oid, "role": "assistant", "content": ai_reply, "created_at": datetime.now(timezone.utc)}
    ])

    # Update state if changed
    if new_state != state:
        await db.tuition_sessions.update_one(
            {"_id": session_oid},
            {"$set": {"session_state": new_state}}
        )

    # Check for conclusion
    if "Class Dismissed" in ai_reply:
        await db.tuition_sessions.update_one(
            {"_id": session_oid},
            {"$set": {"status": "completed"}}
        )

    return {
        "status_code": 200,
        "reply": ai_reply,
        "current_state": new_state,
        "is_completed": "Class Dismissed" in ai_reply
    }
