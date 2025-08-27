from pydantic import BaseModel,field_validator

class UserCreate(BaseModel):
    mobile_number: str
    student_id: str

class Student(BaseModel):
    student_name: str
    dob: str
    student_class: str
    address: str
    guardian_name: str
    parent_mobile: str   # <-- instead of passing student_id, we link with parent number


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