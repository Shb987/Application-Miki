from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class HomeworkRequest(BaseModel):
    student_id: str
    subject: str
    homework_text: Optional[str] = None
    image_url: Optional[str] = None

class DailyTask(BaseModel):
    task_id: str
    title: str
    description: str
    is_completed: bool = False
    due_date: Optional[datetime] = None

class TaskListResponse(BaseModel):
    student_id: str
    tasks: List[DailyTask]

class MentorAdviceRequest(BaseModel):
    student_id: str
    focus_area: Optional[str] = "overall"

class AIResponse(BaseModel):
    role: str
    content: str
    suggestions: List[str] = []
