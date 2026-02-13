from fastapi import APIRouter, Depends, HTTPException
from app.core.database import db
from app.models.companion_models import HomeworkRequest, AIResponse, TaskListResponse, DailyTask
from app.services.ai_companion_service import (
    ai_companion_guide_homework, 
    ai_mentor_advice, 
    ai_parent_insights, 
    ai_coach_tasks
)
from app.utils.user_auth import get_current_user
import uuid
from datetime import datetime

router = APIRouter(prefix="/companion", tags=["AI Student Companion"])

@router.post("/homework/guide", response_model=AIResponse)
async def guide_homework(request: HomeworkRequest, current_user: dict = Depends(get_current_user)):
    """API to guide students through homework task."""
    try:
        content = await ai_companion_guide_homework(
            request.student_id, 
            request.subject, 
            request.homework_text
        )
        return AIResponse(
            role="Companion",
            content=content,
            suggestions=["Ask for a step-by-step breakdown", "Explain this concept further"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mentor/advice/{student_id}", response_model=AIResponse)
async def get_mentor_advice(student_id: str, current_user: dict = Depends(get_current_user)):
    """API for personalized mentorship advice based on performance."""
    try:
        content = await ai_mentor_advice(student_id)
        return AIResponse(
            role="Mentor",
            content=content,
            suggestions=["Show me my strengths", "What should I study next?"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/parent/insights/{student_id}", response_model=AIResponse)
async def get_parent_insights(student_id: str, current_user: dict = Depends(get_current_user)):
    """API for parent insights and tips."""
    try:
        content = await ai_parent_insights(student_id)
        return AIResponse(
            role="Parenting Consultant",
            content=content,
            suggestions=["How can I improve their focus?", "Compare with last month"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/coach/tasks/{student_id}", response_model=TaskListResponse)
async def get_coach_tasks(student_id: str, current_user: dict = Depends(get_current_user)):
    """API for AI Coach suggested daily tasks."""
    try:
        tasks_data = await ai_coach_tasks(student_id)
        # tasks_data is expected to be {'tasks': [{'title': '...', 'description': '...'}]}
        
        tasks_list = []
        for t in tasks_data.get("tasks", []):
            tasks_list.append(DailyTask(
                task_id=str(uuid.uuid4()),
                title=t.get("title", "Task"),
                description=t.get("description", ""),
                is_completed=False,
                due_date=datetime.utcnow()
            ))
            
        return TaskListResponse(
            student_id=student_id,
            tasks=tasks_list
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
