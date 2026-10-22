from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

class SchoolCreate(BaseModel):
    name: str
    link: str

class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    link: Optional[str] = None

class SchoolInDB(SchoolCreate):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

