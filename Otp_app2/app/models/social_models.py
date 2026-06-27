from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ContributorCreate(BaseModel):
    name: str
    username: str
    password: str
    specialization: Optional[str] = None
    status: str = "active"

class ContributorInDB(ContributorCreate):
    id: Optional[str] = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SocialContentCreate(BaseModel):
    title: str
    description: str
    media_url: Optional[str] = None
    media_type: str = "text" # 'video', 'image', 'text'
    target_age_group: Optional[str] = None # e.g., '10-15'
    target_class: Optional[str] = None # e.g., '8th'
    skill_tags: List[str] = [] # User defined tags e.g. ['robotics', 'science']

class SocialContentInDB(SocialContentCreate):
    id: Optional[str] = Field(default=None, alias="_id")
    contributor_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    likes_count: int = 0
    views_count: int = 0

class ContentInteraction(BaseModel):
    student_id: str
    content_id: str
    interaction_type: str # 'like', 'view'
    skill_tags: List[str] = [] # Snapshot of tags at interaction time for analytics
    timestamp: datetime = Field(default_factory=datetime.utcnow)
