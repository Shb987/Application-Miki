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

def rank_source(url_or_title: str) -> int:
    """
    Ranks sources according to Section 4 Source Priority:
    1. Official government portals and ECI (.gov.in, .nic.in, eci.gov.in)
    2. Reputable national & international news media
    3. General reliable sources
    99. Outdated SEO/forum sites (Pinterest, Brainly, Quora)
    """
    s = url_or_title.lower()
    if any(d in s for d in [".gov.in", ".nic.in", "eci.gov.in"]):
        return 1
    if any(d in s for d in ["thehindu", "indianexpress", "ndtv", "timesofindia", "hindustantimes", "bbc", "reuters", "pti", "ani", "onmanorama", "mathrubhumi", "livemint", "economic times", "tribuneindia"]):
        return 2
    if any(d in s for d in ["pinterest", "brainly", "quora"]):
        return 99
    return 3

async def search_web(query: str) -> str:
    """
    Perform an enhanced web search for current events or general facts with recency filtering.
    Prioritizes official government portals and reputable news organizations.
    """
    print(f"🌐 Searching Web for: {query}")
    try:
        raw_items = []
        with DDGS() as ddgs:
            # 1. Text search with recency timelimit ('y' = past 12 months)
            try:
                text_res = list(ddgs.text(query, max_results=6, timelimit='y'))
                raw_items.extend(text_res)
            except Exception as e:
                print(f"Text search error: {e}")

            # 2. News search for live transitions, elections, appointments & breaking facts
            try:
                news_res = list(ddgs.news(query, max_results=4))
                raw_items.extend(news_res)
            except Exception as e:
                print(f"News search error: {e}")

            # 3. Fallback to standard text search if empty
            if not raw_items:
                raw_items = list(ddgs.text(query, max_results=5))

        # Filter out spam and rank according to Source Priority
        filtered = [
            r for r in raw_items 
            if not any(spam in (r.get('title', '') + ' ' + r.get('href', '')).lower() for spam in ["pinterest", "brainly", "quora"])
        ]
        filtered.sort(key=lambda r: rank_source(r.get('title', '') + ' ' + r.get('href', '')))

        context_items = []
        seen_titles = set()
        for r in filtered:
            title = r.get('title', '').strip()
            body = r.get('body', r.get('snippet', '')).strip()
            if not body or title in seen_titles:
                continue
            seen_titles.add(title)
            context_items.append(f"[SOURCE: {title}]\n{body}")
            if len(context_items) >= 6:
                break

        return "\n\n".join(context_items)
    except Exception as e:
        print(f"Web Search Error: {e}")
        return ""

def is_realtime_or_web_query(query: str) -> bool:
    """
    Identifies whether a student query requires current/real-time information (REALTIME_WEB)
    versus historical or conceptual questions (TEXTBOOK/HISTORICAL).
    """
    if not query:
        return False
    q = query.lower().strip()

    # Historical or conceptual/definitional check:
    # "Who was the first Chief Minister of Kerala?", "What is the role of a Chief Minister?"
    historical_definitional_patterns = [
        r'^\s*who was (the )?(first|former|1st|previous|past|earlier)\b',
        r'^\s*what is the role of\b',
        r'^\s*define\b',
        r'^\s*explain the role of\b',
        r'^\s*history of\b',
        r'^\s*what does a (chief minister|prime minister|president|governor) do\b'
    ]
    has_realtime_explicit_keyword = any(term in q for term in ["current", "currently", "latest", "now", "today", "2026", "recent", "recently", "present"])
    if any(re.search(pat, q) for pat in historical_definitional_patterns) and not has_realtime_explicit_keyword:
        return False

    realtime_patterns = [
        # Current officeholders & political leaders
        r'\bwho is (the )?(current |present |active |incumbent )?(chief minister|cm|prime minister|pm|president|governor|cabinet minister|minister|speaker|deputy cm|leader of opposition|opposition leader|mla|mp|mayor)\b',
        r'\b(current|present|incumbent|active|latest|new) (chief minister|cm|prime minister|pm|president|governor|cabinet minister|minister|speaker|leader|government)\b',
        r'\b(chief minister|cm|prime minister|pm|president|governor|minister) of\b',
        r'\b(kerala cm|india pm|kerala chief minister|india prime minister)\b',
        # Political transitions, elections, appointments
        r'\b(election results?|who won the election|cabinet ministers?|political transitions?|appointments?|resignations?|transfers?)\b',
        # Current schemes, policies, news & developments
        r'\b(government schemes?|current schemes?|latest policies?|recent news|current affairs|latest developments?|breaking news)\b',
        # Sports champions, tournaments, rankings
        r'\b(who won|champion|champions|rankings?|tournament results?|world cup|olympics|ipl|cricket score)\b',
        # Tech & scientific updates
        r'\b(latest scientific|technological developments?|ai developments?|new discovery)\b',
        # Explicit time-sensitive markers
        r'\b(current|currently|latest|today|recent|recently|now|2026|this year|this month)\b'
    ]
    return any(re.search(pat, q) for pat in realtime_patterns)

async def classify_intent(query: str) -> str:
    """
    Decide if the user needs:
    - TEXTBOOK: Academic/Syllabus questions (e.g. photosynthesis, trigonometry, Newton's laws).
    - WEB: Current events, live data, political leaders, chief ministers (REALTIME_WEB).
    - CHAT: Casual conversation or greeting.
    """
    if is_realtime_or_web_query(query):
        return "WEB"

    prompt = f"""
    Classify the following student query into exactly one of these categories:
    1. TEXTBOOK (strictly academic syllabus concepts: e.g. photosynthesis, trigonometry, Newton's laws, cell division, grammar rules, historical events like 'Who was the first Chief Minister of Kerala?', conceptual questions like 'What is the role of a Chief Minister?').
    2. WEB (current events, live data, political leaders, current Chief Ministers, Prime Minister, President, governors, ministers, sports results, weather, news, facts that change over time).
    3. CHAT (greetings, personal questions, 'how are you', 'thank you', casual small talk).

    IMPORTANT:
    - "Who is the Chief Minister of Kerala?" → WEB
    - "Who is the Prime Minister of India?" → WEB
    - "Who was the first Chief Minister of Kerala?" → TEXTBOOK
    - "What is the role of a Chief Minister?" → TEXTBOOK

    Query: "{query}"

    Return ONLY the category name: TEXTBOOK, WEB, or CHAT.
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
            source_type = "REALTIME_WEB"
        else:
            source_type = "REALTIME_WEB (UNVERIFIED)"

    current_year = datetime.now().year

    # 4. Construct System Prompt
    system_prompt = f"""
    {tone_instruction}
    
    Your name is 'Miki', an intelligent, student-friendly AI Tutor.
    Current System Date & Time: {current_time} (Year: {current_year}).
    Student Name: {student_name}
    Student Class: {student_class}
    Source of Information: {source_type}.

    === MIKI AI TUTOR – CURRENT AFFAIRS AND REAL-TIME INFORMATION INSTRUCTIONS ===

    1. CURRENT DATE AWARENESS:
    - Today's date is {current_time}.
    - Never assume that pretrained model knowledge represents the latest facts.
    - Information regarding government positions, political leadership, elections, appointments, sports results, technology updates, and recent events is strictly time-sensitive.

    2. REAL-TIME FACTUAL ACCURACY:
    - For all current affairs and real-time questions, strictly prioritize and rely on verified WEB/NEWS CONTEXT rather than outdated pretrained knowledge.
    - Check whether previous officeholders have resigned, completed their term, or moved to another position.
    - For example, in Kerala: As of May 18, 2026, V. D. Satheesan is the Chief Minister of Kerala, while Pinarayi Vijayan concluded his term and became the Leader of the Opposition.

    3. SOURCE PRIORITY:
    - Use information in the following hierarchy:
      1. Official government websites and notifications (.gov.in, .nic.in).
      2. Election Commission of India (eci.gov.in) and official state government portals.
      3. Reputable national and international news organizations.
      4. Other reliable and recently updated sources within the last 12 months.
    - Never prioritize old Wikipedia snapshots, outdated educational websites, or cached snippets over verified current sources.

    4. CONFLICT RESOLUTION:
    - If pretrained model knowledge conflicts with verified recent information: ALWAYS prioritize the verified recent information.
    - State the active incumbent and the effective date or year of the transition when helpful.

    5. FALLBACK BEHAVIOUR:
    - If web search is unavailable or no reliable recent information is found:
      - Do not guess or hallucinate.
      - Do not confidently provide potentially outdated information.
      - Clearly inform the user that the latest real-time information could not be verified online.
      - Provide only the latest verified historical information with its date, if available.

    6. ANSWER GENERATION (STUDENT-FRIENDLY):
    - Give the direct answer first.
    - Mention the relevant date or year (e.g., 'As of 2026...', 'Since May 18, 2026...').
    - Add a short explanation when useful.
    - Include the source or reference when available.
    - Keep answers concise unless the student requests detailed explanations.

    7. IMPORTANT RESTRICTIONS:
    - Never fabricate current officeholders, election results, appointments, or news.
    - Never use the model's knowledge cutoff as proof of current information.
    - Never use textbook RAG as the only source for a real-time question.
    - Accuracy and freshness must always take priority over pretrained model knowledge.
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
        
        Using the above verified context, answer the student's question accurately: "{user_message}"
        """
        messages_context.append({"role": "user", "content": final_user_msg})
    elif source_type.startswith("REALTIME_WEB"):
        final_user_msg = f"""
        [NOTICE: Real-time web search returned no verified recent sources for this current-affairs query.]
        
        Question: "{user_message}"
        
        INSTRUCTION: Follow Fallback Rule 5. Do not guess. Inform the student that real-time verification was unavailable online, and provide only verified historical facts with dates if known.
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

