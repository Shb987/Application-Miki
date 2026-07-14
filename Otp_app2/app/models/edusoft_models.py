from pydantic import BaseModel, Field, field_validator


class EduSoftStoreCredentials(BaseModel):
    student_id: str = Field(..., description="Student ObjectId returned from /api/v1/register-student")
    username: str   = Field(..., description="Auto-generated EduSoft username")
    password: str   = Field(..., description="Auto-generated EduSoft password (will be encrypted and stored)")

    @field_validator("student_id")
    @classmethod
    def validate_student_id(cls, v: str) -> str:
        v = v.strip()
        if len(v) != 24:
            raise ValueError("student_id must be a 24-character hex ObjectId")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("username must not be empty")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v:
            raise ValueError("password must not be empty")
        return v
