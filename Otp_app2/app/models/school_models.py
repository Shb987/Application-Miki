from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SchoolCreate(BaseModel):
    name: str
    link: str

class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    link: Optional[str] = None

class SchoolInDB(SchoolCreate):
    created_at: datetime = datetime.utcnow()
