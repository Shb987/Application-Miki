from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TutorChatRequest(BaseModel):
    student_id: str
    message: str

class ChatMessage(BaseModel):
    role: str  # "user" or "tutor"
    content: str
    timestamp: datetime

class TutorChatHistory(BaseModel):
    student_id: str
    messages: List[ChatMessage]
