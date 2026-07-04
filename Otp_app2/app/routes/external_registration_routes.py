from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from app.core.database import db
from app.core.settings import settings
import re

router = APIRouter()

# ─────────────────────────────────────────────
# 📦 Request Schema
# ─────────────────────────────────────────────

class ExternalStudentRegistration(BaseModel):
    name: str = Field(..., description="Student's full name")
    student_class: str = Field(..., description="Class / Grade (e.g. '5', '10')")
    division: str = Field(..., description="Division / Section (e.g. 'A', 'B')")
    address: str = Field(..., description="Student's residential address")
    dob: str = Field(..., description="Date of birth in YYYY-MM-DD format")
    guardian_name: str = Field(..., description="Name of parent / guardian")
    guardian_phone: str = Field(..., description="Guardian's 10-digit mobile number")
    link: str = Field(..., description="Unique school identifier link (used to look up the school)")

    @field_validator("guardian_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 10:
            raise ValueError("guardian_phone must be a 10-digit number")
        return v

    @field_validator("dob")
    @classmethod
    def validate_dob(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("dob must be in YYYY-MM-DD format")
        return v


# ─────────────────────────────────────────────
# 🔑 API Key Security Dependency
# ─────────────────────────────────────────────

async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """
    Simple API key guard. Partner apps must include the header:
        X-API-Key: <value from EXTERNAL_API_KEY in .env>
    """
    if x_api_key != settings.EXTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return x_api_key


# ─────────────────────────────────────────────
# 🚀 Endpoint
# ─────────────────────────────────────────────

@router.post(
    "/register-student",
    response_model=dict,
    summary="External student registration",
    description=(
        "Called by partner web applications at registration time. "
        "Creates a student record and links it to the school identified by `link`."
    ),
    tags=["External Registration"]
)
async def external_register_student(
    payload: ExternalStudentRegistration,
    _: str = Depends(verify_api_key)
):
    # ── 1. Resolve school by link or Auto-Create ───────────────────────────
    school = await db.schools.find_one({"link": payload.link})
    if not school:
        import urllib.parse
        parsed = urllib.parse.urlparse(payload.link)
        if parsed.netloc:
            # Extract subdomain (e.g., from 'school.onedusoft.in', get 'school')
            raw_name = parsed.netloc.split('.')[0]
            school_name = raw_name.replace("-", " ").replace("_", " ").title()
        else:
            school_name = payload.link.replace("-", " ").replace("_", " ").title()
        new_school = {
            "name": school_name,
            "link": payload.link,
            "created_at": datetime.now(timezone.utc),
            "student_count": 0
        }
        result = await db.schools.insert_one(new_school)
        school_id = str(result.inserted_id)
    else:
        school_id = str(school["_id"])
        school_name = school.get("name", "")

    # ── 2. Prevent duplicate registration (same name + dob + school) ───────
    existing_student = await db.students.find_one({
        "student_name": payload.name,
        "dob": payload.dob,
        "school_id": school_id
    })
    if existing_student:
        return {
            "status": "already_registered",
            "message": "Student is already registered in this school.",
            "student_id": str(existing_student["_id"]),
            "school_id": school_id,
            "school_name": school_name
        }

    # ── 3. Fetch default subscription plan ────────────────────────────────
    basic_plan = await db.subscription_plans.find_one({"_id": "basic"})
    initial_buckets = basic_plan.get("buckets", {}) if basic_plan else {
        "exam_balance": 1,
        "voice_balance_mins": 2,
        "tutor_balance_qs": 5,
        "class_balance": 0
    }

    # ── 4. Build student document ─────────────────────────────────────────
    student_doc = {
        "student_name": payload.name,
        "dob": payload.dob,
        "student_class": payload.student_class,
        "division": payload.division,
        "address": payload.address,
        "guardian_name": payload.guardian_name,
        "school_id": school_id,
        "image_url": None,
        "created_at": datetime.now(timezone.utc),
        "registered_via": "external_api",          # track the source
        "subscription": {
            "current_tier": "basic",
            "last_recharge_date": None
        },
        "usage_buckets": initial_buckets,
        "is_user": False,
        "is_new_user": True
    }

    student_result = await db.students.insert_one(student_doc)
    student_oid = student_result.inserted_id

    # ── 5. Link parent / guardian in usertable ────────────────────────────
    await db.usertable.update_one(
        {"mobile_number": payload.guardian_phone},
        {
            "$setOnInsert": {
                "usertype": "parent",
                "created_at": datetime.now(timezone.utc)
            },
            "$addToSet": {
                "student_ids": student_oid
            }
        },
        upsert=True
    )

    # ── 6. Update school's student count (optional convenience counter) ───
    from bson import ObjectId
    await db.schools.update_one(
        {"_id": ObjectId(school_id)},
        {
            "$inc": {"student_count": 1},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    )

    return {
        "status": "success",
        "message": "Student registered successfully",
        "student_id": str(student_oid),
        "school_id": school_id,
        "school_name": school_name,
        "guardian_phone": payload.guardian_phone
    }
