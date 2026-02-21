from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class SpecialDayBase(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    activity: Optional[str] = Field(None, description="Suggested activity for students")
    image_url: Optional[str] = None
    type: str = Field("Event", description="Holiday, Event, Exam, Celebration")
    is_active: bool = True

class SpecialDayCreate(SpecialDayBase):
    pass

class SpecialDayUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    activity: Optional[str] = None
    image_url: Optional[str] = None
    type: Optional[str] = None
    is_active: Optional[bool] = None

class SpecialDayResponse(SpecialDayBase):
    id: str
    created_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}
