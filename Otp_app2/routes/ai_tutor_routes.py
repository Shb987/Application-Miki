from fastapi import APIRouter, Depends, HTTPException
from core.database import db
from utils.user_auth import get_current_user
from models.ai_tutor_models import TutorChatRequest, ChatMessage, TutorChatHistory
from datetime import datetime, timezone
import os
from openai import AsyncOpenAI
from bson import ObjectId

from duckduckgo_search import DDGS

router = APIRouter(prefix="/ai-tutor", tags=["AI Tutor"])

# Initialize OpenAI Client (Async)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
        intent = response.choices[0].message.content.strip().upper()
        # Fallback cleanup
        if "TEXTBOOK" in intent: return "TEXTBOOK"
        if "WEB" in intent: return "WEB"
        return "CHAT"
    except:
        return "CHAT"

# -----------------------------------------------------------------------------
# 💬 CHAT ENDPOINT
# -----------------------------------------------------------------------------
@router.post("/chat")
async def chat_with_tutor(payload: TutorChatRequest, current_user: dict = Depends(get_current_user)):
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
