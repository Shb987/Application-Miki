from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

class VoiceChatHistory(BaseModel):
    student_id: str = Field(..., description="The ID of the student")
    session_id: str = Field(..., description="Unique identifier for the chat session")
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="The transcribed text content")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VoiceSessionInfo(BaseModel):
    student_id: str
    session_id: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
