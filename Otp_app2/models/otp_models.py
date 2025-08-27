from pydantic import BaseModel, field_validator

class OTPRequest(BaseModel):
    mobile_number: str

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 10 or not v.startswith(("6", "7", "8", "9")):
            raise ValueError("Invalid mobile number")
        return v

class OTPVerify(BaseModel):
    mobile_number: str
    otp: str

    @field_validator("mobile_number")
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
