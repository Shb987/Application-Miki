from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SchoolCreate(BaseModel):
    name: str
    place_code: str
    link: Optional[str] = None
    status: str = "active"  # active or inactive
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None

class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    place_code: Optional[str] = None
    link: Optional[str] = None
    status: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None

class SchoolInDB(SchoolCreate):
    created_at: datetime = datetime.utcnow()
