from pydantic import BaseModel, field_validator
from typing import Optional, Dict, Any
from datetime import datetime

class UserCreate(BaseModel):
    mobile_number: str
    student_id: str

class UsageBuckets(BaseModel):
    exam_balance: int = 1
    voice_balance_mins: int = 2
    tutor_balance_qs: int = 5
    class_balance: int = 2

class SubscriptionInfo(BaseModel):
    current_tier: str = "basic"
    last_recharge_date: Optional[datetime] = None

class Student(BaseModel):
    student_name: str
    dob: str
    student_class: str
    age: str
    address: str
    guardian_name: str
    parent_mobile: str
    image_url: Optional[str] = None
    subscription: Optional[SubscriptionInfo] = SubscriptionInfo()
    usage_buckets: Optional[UsageBuckets] = UsageBuckets()
    school_id: Optional[str] = None


class StudentUpdate(BaseModel):
    student_name: Optional[str] = None
    dob: Optional[str] = None
    student_class: Optional[str] = None
    age: Optional[str] = None
    address: Optional[str] = None
    guardian_name: Optional[str] = None
    image_url: Optional[str] = None
    school_id: Optional[str] = None

    @field_validator("age")
    @classmethod
    def validate_age(cls, v):
        if v is not None and not v.isdigit():
            raise ValueError("Age must be numeric")
        return v


class UserTypeRequest(BaseModel):
    mobile_number: str
    usertype: str

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 10 or not v.startswith(("6", "7", "8", "9")):
            raise ValueError("Invalid mobile number")
        return v

    @field_validator("usertype")
    @classmethod
    def validate_usertype(cls, v: str) -> str:
        allowed = {"parent", "student"}
        if v.lower() not in allowed:
            raise ValueError("usertype must be 'parent' or 'student'")
        return v.lower()

class MobileChangeRequest(BaseModel):
    new_mobile_number: str
    otp: str

    @field_validator("new_mobile_number")
    @classmethod
    def validate_mobile_number(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 10 or not v.startswith(("6", "7", "8", "9")):
            raise ValueError("Invalid mobile number")
        return v

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Invalid OTP format")
        return v