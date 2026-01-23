from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class GroupCreate(BaseModel):
    name: str
    member_ids: List[str]  # List of student ObjectIds as strings

class GroupResponse(BaseModel):
    id: str
    name: str
    class_name: str
    member_ids: List[str]
    created_by: str
    created_at: datetime

class ChatMessage(BaseModel):
    id: Optional[str] = None
    group_id: str
    sender_id: str
    sender_name: str
    message: str
    timestamp: datetime
