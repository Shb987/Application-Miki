from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class VideoLink(BaseModel):
    title: str
    published_at: str
    link: str

class TutorialModule(BaseModel):
    student_class: str
    subject: str
    topic: Optional[str] = None
    youtube_url: str
    video_links: List[VideoLink] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class YouTubeFetchRequest(BaseModel):
    youtube_url: str
    student_class: str
    subject: str
    topic: Optional[str] = None
