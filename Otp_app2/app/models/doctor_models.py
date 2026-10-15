from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime

SPECIALIZATION_OPTIONS = [
    "Mental Health Counselor",
    "Child Psychologist",
    "Clinical Psychologist",
    "Psychiatrist",
    "Speech Therapist",
    "Speech-Language Therapist",
    "Audiologist",
    "Occupational Therapist",
    "Developmental Specialist",
    "Special Educator",
    "Other"
]

class DoctorBase(BaseModel):
    doctor_name: str = Field(..., description="Full name of the doctor")
    profile_image: Optional[str] = Field(None, description="URL or relative path to uploaded profile image")
    specialization: str = Field(..., description="Specialization from predefined list")
    other_specialization: Optional[str] = Field(None, description="Custom specialization if 'Other' is chosen")
    qualification: str = Field(..., description="Academic and medical qualifications")
    experience: float = Field(..., description="Years of professional experience", ge=0)
    hospital_clinic_name: Optional[str] = Field(None, description="Hospital or clinic name")
    consultation_address: Optional[str] = Field(None, description="Consultation or clinic address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    contact_number: Optional[str] = Field(None, description="Contact phone number")
    email: Optional[str] = Field(None, description="Email address")
    available_days: Optional[List[str]] = Field(default_factory=list, description="List of days doctor is available")
    available_time: Optional[str] = Field(None, description="Available consultation time slots")
    short_biography: Optional[str] = Field(None, description="Brief professional biography")
    status: str = Field("Active", description="Profile status: Active or Inactive")
    is_active: bool = Field(True, description="Boolean flag indicating active status")

class DoctorCreate(DoctorBase):
    pass

class DoctorUpdate(BaseModel):
    doctor_name: Optional[str] = None
    profile_image: Optional[str] = None
    specialization: Optional[str] = None
    other_specialization: Optional[str] = None
    qualification: Optional[str] = None
    experience: Optional[float] = None
    hospital_clinic_name: Optional[str] = None
    consultation_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    available_days: Optional[List[str]] = None
    available_time: Optional[str] = None
    short_biography: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None

class DoctorStatusUpdate(BaseModel):
    status: Optional[str] = None
    is_active: Optional[bool] = None

class DoctorResponse(DoctorBase):
    id: str
    doctor_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

class DoctorPublicResponse(BaseModel):
    doctor_id: str
    doctor_name: str
    profile_image: Optional[str] = None
    profile_image_url: Optional[str] = None
    specialization: str
    other_specialization: Optional[str] = None
    qualification: str
    experience: float
    hospital_clinic_name: Optional[str] = None
    consultation_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    available_days: Optional[List[str]] = []
    available_time: Optional[str] = None
    short_biography: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[str] = None
    status: str = "Active"
    is_active: bool = True
