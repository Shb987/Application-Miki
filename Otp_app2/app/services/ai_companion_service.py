import os
import json
from openai import AsyncOpenAI
from typing import List, Optional
from app.core.database import db
from bson import ObjectId

# Load environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or "sk-placeholder"
client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=20.0)

async def get_student_performance_context(student_id: str):
    """Fetches recent evaluations and scores to give the AI context."""
    # student_id is now the standard 24-char ObjectID hex string
    evaluations = await db.evaluations.find({"student_id": ObjectId(student_id)}).sort("completed_at", -1).to_list(5)
    
    context = "Recent Performance:\n"
    if not evaluations:
        context += "No evaluation history yet.\n"
    else:
        for ev in evaluations:
            score = ev.get("total_score", 0)
            max_s = ev.get("max_total", 0)
            status = ev.get("status", "N/A")
            context += f"- Evaluation {ev.get('evaluation_id')}: {score}/{max_s} ({status})\n"
    
    return context

async def ai_companion_guide_homework(student_id: str, subject: str, homework_text: str):
    """AI Companion guides the student through homework using Socratic questioning."""
    
    system_prompt = f"""
    You are an AI Student Companion. Your goal is to guide the student through their homework for {subject}.
    CRITICAL: Do NOT give the direct answer. Instead, ask guiding questions, explain underlying concepts, 
    and break the problem into smaller steps. Be encouraging and helpful.
    """
    
    user_prompt = f"Student ID: {student_id}\nHomework Task: {homework_text}"
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    # Log usage
    if hasattr(response, 'usage') and response.usage:
        from app.utils.ai_usage_logger import log_ai_usage
        await log_ai_usage(student_id, "Companion - Homework Guide", "gpt-4o-mini", response.usage)

    return response.choices[0].message.content

async def ai_mentor_advice(student_id: str):
    """AI Mentor provides personalized motivation and learning paths."""
    
    performance_context = await get_student_performance_context(student_id)
    
    system_prompt = """
    You are an AI Mentor. Analyze the student's performance and provide motivational advice.
    Focus on areas of improvement, celebrate their wins, and suggest a personalized learning path.
    Keep the tone inspiring and supportive.
    """
    
    user_prompt = f"Student Performance Context:\n{performance_context}"
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.8
    )
    
    # Log usage
    if hasattr(response, 'usage') and response.usage:
        from app.utils.ai_usage_logger import log_ai_usage
        await log_ai_usage(student_id, "Companion - Mentor Advice", "gpt-4o-mini", response.usage)

    return response.choices[0].message.content

async def ai_parent_insights(student_id: str):
    """AI Parenting Consultant providing feedback to parents."""
    
    performance_context = await get_student_performance_context(student_id)
    
    system_prompt = """
    You are an AI Parenting Consultant. Provide professional, empathetic insights to the parent 
    about their child's academic progress. Suggest ways they can support their child at home.
    """
    
    user_prompt = f"Child's (Student ID: {student_id}) Performance Context:\n{performance_context}"
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    
    # Log usage
    if hasattr(response, 'usage') and response.usage:
        from app.utils.ai_usage_logger import log_ai_usage
        await log_ai_usage(student_id, "Companion - Parent Insights", "gpt-4o-mini", response.usage)

    return response.choices[0].message.content

async def ai_coach_tasks(student_id: str):
    """AI Coach breaks down goals into daily tasks."""
    
    # We could fetch the upcoming exam or curriculum here if available.
    # For now, we'll base it on general academic improvement.
    
    system_prompt = """
    You are an AI Habit & Skill Coach. Your task is to provide 3-5 specific, actionable daily tasks 
    for the student to improve their study habits and master their current subjects.
    Return the response in a JSON list of objects with 'title' and 'description'.
    """
    
    user_prompt = f"Generate daily tasks for Student ID: {student_id} to improve study routine."
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini", # Using mini for task generation
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    # Log usage
    if hasattr(response, 'usage') and response.usage:
        from app.utils.ai_usage_logger import log_ai_usage
        await log_ai_usage(student_id, "Companion - Coach Tasks", "gpt-4o-mini", response.usage)
        
    return json.loads(response.choices[0].message.content)
