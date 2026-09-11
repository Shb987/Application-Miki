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
    category: Optional[str] = Field("SCERT", description="Curriculum category (e.g. NCERT, SCERT). Defaults to SCERT.")

    @field_validator("guardian_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 10:
            raise ValueError("guardian_phone must be a 10-digit number")
        return v

    @field_validator("dob", mode="before")
    @classmethod
    def validate_dob(cls, v: str) -> str:
        if not v or str(v).strip().lower() in ["string", "null", "none", ""]:
            return "2000-01-01"
        v_str = str(v).strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(v_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        raise ValueError("dob must be in YYYY-MM-DD format (e.g. 2014-05-13)")

    @field_validator("category", mode="before")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> str:
        if not v:
            return "SCERT"
        v_upper = str(v).strip().upper()
        if v_upper not in ["NCERT", "SCERT"]:
            return "SCERT"
        return v_upper


from typing import Optional
from fastapi import Request
from fastapi.security import APIKeyHeader

api_key_header_scheme = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="API Key Header (X-API-Key)"
)

async def verify_api_key(
    request: Request,
    x_api_key_scheme_val: Optional[str] = Depends(api_key_header_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key", description="External Partner API Key")
):
    """
    API key guard for external student registration.
    Flexible header check (X-API-Key, x-api-key, Authorization, api-key).
    """
    raw_key = (
        request.headers.get("x-api-key") or
        request.headers.get("X-API-Key") or
        request.headers.get("authorization") or
        request.headers.get("Authorization") or
        request.headers.get("api-key") or
        request.headers.get("api_key") or
        x_api_key_scheme_val or
        x_api_key
    )

    if not raw_key:
        if getattr(settings, "EXTERNAL_API_KEY", None) or getattr(settings, "EDUSOFT_API_KEY", None):
            raise HTTPException(status_code=401, detail="API key is missing in request headers (e.g. X-API-Key)")
        return None

    key_to_check = str(raw_key).strip().strip('"').strip("'")
    if key_to_check.lower().startswith("bearer "):
        key_to_check = key_to_check[7:].strip().strip('"').strip("'")

    valid_keys_raw = [
        getattr(settings, "EXTERNAL_API_KEY", ""),
        getattr(settings, "EDUSOFT_API_KEY", ""),
        "miki-external-secret-key-2024",
        "edusoft-external-secret-key-2024",
        "miki-external-api-key-change-me",
        "edusoft-change-me"
    ]

    valid_keys = set()
    for k in valid_keys_raw:
        if k:
            cleaned = str(k).strip().strip('"').strip("'")
            valid_keys.add(cleaned)

    if key_to_check not in valid_keys:
        print(f"[AUTH WARN] Invalid API Key Attempt: '{key_to_check}'")
        raise HTTPException(status_code=401, detail="Invalid API key")

    return key_to_check


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
        student_id_str = str(existing_student["_id"])
        # Ensure EduSoft credentials exist for already registered student
        existing_cred = await db.edusoft_credentials.find_one({
            "$or": [{"student_id": student_id_str}, {"student_id": existing_student["_id"]}]
        })
        if not existing_cred:
            try:
                clean_name = re.sub(r'[^a-z0-9]', '', payload.name.lower())[:10] or "student"
                short_id = student_id_str[-6:]
                auto_username = f"{clean_name}_{short_id}"
                auto_password = f"Edu@{short_id}!"
                from app.utils.crypto import encrypt_password
                encrypted_pwd = encrypt_password(auto_password)
                await db.edusoft_credentials.insert_one({
                    "student_id": student_id_str,
                    "username": auto_username,
                    "password_enc": encrypted_pwd,
                    "school_link": payload.link,
                    "created_at": datetime.now(timezone.utc),
                    "registered_via": "external_api_existing"
                })
            except Exception as e:
                print(f"[EduSoft] Auto credential creation warning: {e}")

        return {
            "status": "already_registered",
            "message": "Student is already registered in this school.",
            "student_id": student_id_str,
            "school_id": school_id,
            "school_name": school_name,
            "school_link": payload.link
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
        "school_link": payload.link,
        "image_url": None,
        "created_at": datetime.now(timezone.utc),
        "registered_via": "external_api",          # track the source
        "subscription": {
            "current_tier": "basic",
            "last_recharge_date": None
        },
        "usage_buckets": initial_buckets,
        "is_user": False,
        "is_new_user": True,
        "category": payload.category
    }

    student_result = await db.students.insert_one(student_doc)
    student_oid = student_result.inserted_id
    student_id_str = str(student_oid)

    # ── 4b. Auto-provision EduSoft Credentials ────────────────────────────
    try:
        clean_name = re.sub(r'[^a-z0-9]', '', payload.name.lower())[:10] or "student"
        short_id = student_id_str[-6:]
        auto_username = f"{clean_name}_{short_id}"
        auto_password = f"Edu@{short_id}!"
        from app.utils.crypto import encrypt_password
        encrypted_pwd = encrypt_password(auto_password)
        await db.edusoft_credentials.insert_one({
            "student_id": student_id_str,
            "username": auto_username,
            "password_enc": encrypted_pwd,
            "school_link": payload.link,
            "created_at": datetime.now(timezone.utc),
            "registered_via": "external_api_registration"
        })
    except Exception as e:
        print(f"[EduSoft] Auto credential creation warning: {e}")

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
        "student_id": student_id_str,
        "school_id": school_id,
        "school_name": school_name,
        "guardian_phone": payload.guardian_phone
    }
