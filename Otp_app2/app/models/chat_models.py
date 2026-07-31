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
    image_url: Optional[str] = None
    created_by: str
    created_at: datetime

class SharedPostCard(BaseModel):
    content_id: str
    title: str
    description: str          # Short preview of the post body
    media_type: str           # 'text', 'image', 'video'
    media_url: Optional[str] = None  # Thumbnail or video URL
    skill_tags: List[str] = []
    contributor_name: str = "Unknown"

class ChatMessage(BaseModel):
    id: Optional[str] = None
    group_id: str
    sender_id: str
    sender_name: str
    message: str
    message_type: str = "text"                   # "text" | "shared_post"
    shared_post: Optional[SharedPostCard] = None # Only present when message_type = "shared_post"
    timestamp: datetime
