from fastapi import APIRouter, Depends, HTTPException
from app.core.database import db
from app.utils.user_auth import get_current_user
from app.models.ai_tutor_models import TutorChatRequest, ChatMessage, TutorChatHistory
from datetime import datetime, timezone
import os
import re
from openai import AsyncOpenAI
from bson import ObjectId
from app.utils.ai_usage_logger import log_ai_usage
from fastapi import BackgroundTasks
from app.utils.usage_guard import check_and_use_quota

try:
    from duckduckgo_search import DDGS
except ImportError:
    from ddgs import DDGS
import numpy as np

router = APIRouter(prefix="/ai-tutor", tags=["AI Tutor"])

# Initialize OpenAI Client (Async)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or "sk-placeholder")

async def search_web(query: str) -> str:
    """Perform a web search for current events or general facts."""
    print(f"🌐 Searching Web for: {query}")
    try:
        # DDGS().text is synchronous, so we wrap it or just run it (it's fast enough for a demo)
        results = DDGS().text(query, max_results=3)
        if not results:
            return ""
        
        context = ""
        for r in results:
            context += f"\n[WEB SOURCE: {r['title']}]\n{r['body']}\n"
        return context
    except Exception as e:
        print(f"Web Search Error: {e}")
        return ""

async def classify_intent(query: str) -> str:
    """
    Decide if the user needs:
    - TEXTBOOK: Academic/Syllabus questions.
    - WEB: Current events, facts clearly outside textbook (e.g. 'Who is the Prime Minister?').
    - CHAT: Casual conversation or greeting.
    """
    prompt = f"""
    Classify the following student query into exactly one of these categories:
    1. TEXTBOOK (related to school subjects, chapters, definitions, science, history, math).
    2. WEB (current events, live data, specific external facts like 'weather', 'news', 'who won').
    3. CHAT (greetings, personal questions, 'how are you', 'thank you').

    Query: "{query}"

    Return ONLY the category name.
    """
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini", # Use cheaper model for routing
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        
        # Log usage
        if hasattr(response, 'usage') and response.usage:
            from app.utils.ai_usage_logger import log_ai_usage
            await log_ai_usage("ADMIN", "AI Tutor - Intent", "gpt-4o-mini", response.usage)

        intent = response.choices[0].message.content.strip().upper()
        # Fallback cleanup
        if "TEXTBOOK" in intent: return "TEXTBOOK"
        if "WEB" in intent: return "WEB"
        return "CHAT"
    except:
        return "CHAT"

async def get_relevant_context(student_class: str, query: str) -> str:
    """
    Retrieves relevant textbook content using Vector Search (Cosine Similarity).
    1. Embeds the user query.
    2. Fetches all chapters for the student's class.
    3. Ranks chapters by similarity and returns the top matches.
    """
    print(f"🔍 Searching Textbook Context for Class {student_class}...")
    
    # 1. Generate Embedding for Query
    try:
        response = await client.embeddings.create(
            model="text-embedding-3-large",
            input=query
        )
        
        # Log usage
        if hasattr(response, 'usage') and response.usage:
            from app.utils.ai_usage_logger import log_ai_usage
            await log_ai_usage("ADMIN", "AI Tutor - Context", "text-embedding-3-large", response.usage)

        query_vector = response.data[0].embedding
    except Exception as e:
        print(f"Embedding Error: {e}")
        return ""

    # 2. Fetch all chapters for this class
    # Note: For production with large datasets, use Atlas Vector Search. 
    # For now, in-memory cosine similarity is sufficient for <1000 chapters.
    try:
        cursor = db.textbook_chapters.find({"standard": str(student_class)})
        chapters = await cursor.to_list(length=None)
    except Exception as e:
        print(f"Database Error: {e}")
        return ""

    if not chapters:
        print("No textbooks found for this class.")
        return ""

    # 3. Compute Cosine Similarity
    def cosine_similarity(v1, v2):
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)

    scored_chapters = []
    for ch in chapters:
        if "vector" not in ch:
            continue
        try:
            score = cosine_similarity(query_vector, ch["vector"])
            scored_chapters.append((score, ch))
        except Exception:
            continue

    # 4. Sort and Top-K
    scored_chapters.sort(key=lambda x: x[0], reverse=True)
    top_3 = scored_chapters[:3]

    # 5. Format Context
    context_text = ""
    for score, ch in top_3:
        # Threshold: Only include if somewhat relevant (e.g., > 0.25)
        if score > 0.25: 
            snippet = ch.get('content', '')[:1500] # Limit chunk size
            context_text += f"\n[TEXTBOOK: {ch.get('subject', 'General')} - {ch.get('chapter_title', '')}]\n{snippet}...\n"
            
    return context_text

def is_exit_or_stop_command(message: str) -> bool:
    """Detect if the student wants to stop, leave, close, or exit the session."""
    if not message:
        return False
    msg = message.strip().lower()
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', msg)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    stop_phrases = [
        "stop everything and leve miki",
        "stop everything and leave miki",
        "stop everything",
        "leave miki",
        "leve miki",
        "stop miki",
        "exit miki",
        "bye miki",
        "goodbye miki",
        "stop chat",
        "end chat",
        "stop session",
        "end session",
        "stop talking",
        "stop now",
        "see you later",
        "talk to you later"
    ]
    for sp in stop_phrases:
        if sp in cleaned:
            return True

    words = cleaned.split()
    if words and words[0] in ["stop", "exit", "quit", "leave", "leve", "bye", "goodbye"]:
        return True

    return False

# -----------------------------------------------------------------------------
# 💬 CHAT ENDPOINT
# -----------------------------------------------------------------------------
@router.post("/chat")
async def chat_with_tutor(payload: TutorChatRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """
    Hybrid Agent Miki:
    - Routes to [Textbook RAG] vs [Web Search] vs [Chat]
    - Adapts tone based on student class level.
    """
    student_id = payload.student_id
    user_message = payload.message

    # 1. Verify Student
    student = await db.students.find_one({"_id": ObjectId(student_id)})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
        
    student_class = str(student.get("student_class", "general"))
    student_name = student.get("student_name", "Student")

    # 🛑 Handle Exit / Stop / Leave commands (Zero quota cost)
    if is_exit_or_stop_command(user_message):
        farewell_reply = (
            f"Goodbye, {student_name}! 👋 I've stopped our session as you requested. "
            "Whenever you are ready to study, ask questions, or learn something new, Miki will be right here for you. "
            "Have a wonderful day! 🌟"
        )
        new_messages = [
            {"role": "user", "content": user_message, "timestamp": datetime.now(timezone.utc)},
            {"role": "assistant", "content": farewell_reply, "timestamp": datetime.now(timezone.utc)}
        ]
        await db.ai_tutor_chats.update_one(
            {"student_id": student_id},
            {
                "$set": {"updated_at": datetime.now(timezone.utc)},
                "$push": {"messages": {"$each": new_messages}}
            },
            upsert=True
        )
        return {
            "status": "success",
            "student_id": student_id,
            "reply": farewell_reply,
            "source": "SESSION_END"
        }

    # 2. Determine Teacher Persona (Adaptive Tone)
    try:
        class_num = int(student_class)
    except:
        class_num = 8 # Default to middle school if unknown

    if class_num <= 5:
        tone_instruction = """
        You are a kind, energetic PRIMARY SCHOOL TEACHER. 
        - Use simple words and fun analogies. 
        - Be very encouraging (use emojis like 🌟, 📚).
        - Keep explanations short and playful.
        """
    elif class_num <= 10:
        tone_instruction = """
        You are a helpful HIGH SCHOOL TEACHER.
        - Be clear, structured, and informative.
        - Encourage critical thinking.
        - Use a professional but approachable tone.
        """
    else:
        tone_instruction = """
        You are a PROFESSOR / SENIOR TUTOR.
        - Provide detailed, academic answers.
        - Focus on concepts and depth.
        - Treat the student as a young adult learner.
        """

    current_time = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")

    # 3. Router: Classify Intent
    intent = await classify_intent(user_message)
    print(f"🧠 Intent Classified: {intent}")

    rag_context = ""
    source_type = "GENERAL KNOWLEDGE"

    # 🚨 Quota is ONLY checked and deducted for Academic / Factual Questions (Textbook or Web Search)
    # Casual chat, greetings, and small talk are free!
    if intent in ["TEXTBOOK", "WEB"]:
        try:
            await check_and_use_quota(student_id, "tutor", cost=1)
        except HTTPException as he:
            if he.status_code == 402:
                quota_reply = (
                    f"🌟 Hello {student_name}! You've reached your daily question limit for today. "
                    "To ask more questions, you can upgrade your plan or recharge your balance, "
                    "or come back tomorrow when your daily free questions refill! "
                    "Feel free to chat casually or review previous topics anytime. 📚"
                )
                new_messages = [
                    {"role": "user", "content": user_message, "timestamp": datetime.now(timezone.utc)},
                    {"role": "assistant", "content": quota_reply, "timestamp": datetime.now(timezone.utc)}
                ]
                await db.ai_tutor_chats.update_one(
                    {"student_id": student_id},
                    {
                        "$set": {"updated_at": datetime.now(timezone.utc)},
                        "$push": {"messages": {"$each": new_messages}}
                    },
                    upsert=True
                )
                return {
                    "status": "quota_exceeded",
                    "student_id": student_id,
                    "reply": quota_reply,
                    "source": "LIMIT_REACHED",
                    "quota_exceeded": True
                }
            raise he

    if intent == "TEXTBOOK":
        rag_context = await get_relevant_context(student_class, user_message)
        if rag_context:
            source_type = "TEXTBOOK"
        else:
            # Fallback if textbook lookup fails (empty) -> maybe try web if it seems important? 
            # For now, just rely on GPT's internal knowledge but keep source type General.
            pass

    elif intent == "WEB":
        rag_context = await search_web(user_message)
        if rag_context:
            source_type = "WEB SEARCH"

    # 4. Construct System Prompt
    system_prompt = f"""
    {tone_instruction}
    
    Your name is 'Miki'. 
    Current Date & Time: {current_time}.
    Student Name: {student_name}
    Student Class: {student_class}
    
    INSTRUCTIONS:
    - You are helping the student with their query.
    - Source of Information: {source_type}.
    - If specific CONTEXT is provided below, usage it STRICTLY to answer.
    - If the student asks about current events (weather, news), use the provided WEB CONTEXT.
    - If it's a casual chat, just be friendly.
    """

    messages_context = [{"role": "system", "content": system_prompt}]

    # 5. Chat History (Context Window)
    history_obj = await db.ai_tutor_chats.find_one({"student_id": student_id})
    if history_obj:
        recent_msgs = history_obj.get("messages", [])[-6:] 
        for m in recent_msgs:
            messages_context.append({"role": m["role"], "content": m["content"]})

    # 6. Add Context & User Query
    if rag_context:
        final_user_msg = f"""
        CONTEXT ({source_type}):
        {rag_context}
        
        Using the above context, answer: "{user_message}"
        """
        messages_context.append({"role": "user", "content": final_user_msg})
    else:
        messages_context.append({"role": "user", "content": user_message})

    # 7. Generate Response
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages_context,
            temperature=0.7
        )
        ai_reply = response.choices[0].message.content
        
        # Log Token Usage
        if hasattr(response, 'usage') and response.usage:
            background_tasks.add_task(
                log_ai_usage,
                student_id=student_id,
                action_type="AI Tutor",
                model="gpt-4o",
                usage_obj=response.usage
            )
            
    except Exception as e:
        print(f"AI Error: {e}")
        ai_reply = "I'm having a bit of trouble connecting to my brain right now. Can you try again?"

    # 8. Save Conversation (Original user message, not the RAG-bloated one)
    new_messages = [
        {"role": "user", "content": user_message, "timestamp": datetime.now(timezone.utc)},
        {"role": "assistant", "content": ai_reply, "timestamp": datetime.now(timezone.utc)}
    ]
    
    await db.ai_tutor_chats.update_one(
        {"student_id": student_id},
        {
            "$set": {"updated_at": datetime.now(timezone.utc)},
            "$push": {"messages": {"$each": new_messages}}
        },
        upsert=True
    )

    return {
        "status": "success",
        "student_id": student_id,
        "reply": ai_reply,
        "source": source_type
    }

@router.get("/history/{student_id}")
async def get_chat_history(student_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch past conversational history"""
    history = await db.ai_tutor_chats.find_one({"student_id": student_id})
    
    if not history:
        return {"messages": []}
        
    return {"messages": history.get("messages", [])}

@router.get("/quota/{student_id}")
async def get_tutor_quota(student_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch the student's remaining tutor questions and daily limit"""
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    tier = student.get("subscription", {}).get("current_tier", "basic")
    buckets = student.get("usage_buckets", {})
    balance = buckets.get("tutor_balance_qs", 0)

    basic_plan = await db.subscription_plans.find_one({"_id": tier})
    daily_limit = basic_plan.get("buckets", {}).get("tutor_balance_qs", 15) if basic_plan else 15

    return {
        "status": "success",
        "student_id": student_id,
        "current_tier": tier,
        "tutor_balance_qs": balance,
        "daily_limit": daily_limit
    }

@router.post("/refill-quota/{student_id}")
async def refill_tutor_quota(student_id: str, amount: int = 25, current_user: dict = Depends(get_current_user)):
    """Refill or add tutor questions to a student for testing or manual recharge"""
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    await db.students.update_one(
        {"_id": s_oid},
        {
            "$inc": {"usage_buckets.tutor_balance_qs": amount},
            "$set": {
                "subscription.quota_upgraded_v2": True,
                "subscription.last_tutor_reset_date": datetime.now(timezone.utc)
            }
        }
    )

    updated_student = await db.students.find_one({"_id": s_oid})
    new_bal = updated_student.get("usage_buckets", {}).get("tutor_balance_qs", 0)

    return {
        "status": "success",
        "message": f"Successfully refilled {amount} tutor questions.",
        "new_tutor_balance": new_bal
    }

