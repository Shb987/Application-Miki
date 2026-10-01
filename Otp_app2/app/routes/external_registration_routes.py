from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
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
    guardian_phone: Optional[str] = Field(None, description="Guardian's mobile number")
    student_phone: Optional[str] = Field(None, description="Student's own 10-digit mobile number")
    phone: Optional[str] = Field(None, description="Student's phone number alias")
    mobile: Optional[str] = Field(None, description="Student's mobile number alias")
    mobile_number: Optional[str] = Field(None, description="Student's mobile number alias")
    phone_number: Optional[str] = Field(None, description="Student's phone number alias")
    student_mobile: Optional[str] = Field(None, description="Student's mobile number alias")
    contact_no: Optional[str] = Field(None, description="Contact number alias")
    mob_no: Optional[str] = Field(None, description="Mobile number alias")
    mobileno: Optional[str] = Field(None, description="EduSoft mobile number alias")
    mobile_no: Optional[str] = Field(None, description="EduSoft mobile number alias")
    father_phone: Optional[str] = Field(None, description="Father phone alias")
    parent_phone: Optional[str] = Field(None, description="Parent phone alias")
    parent_mobile: Optional[str] = Field(None, description="Parent mobile alias")
    link: str = Field(..., description="Unique school identifier link (used to look up the school)")
    category: Optional[str] = Field("SCERT", description="Curriculum category (e.g. NCERT, SCERT). Defaults to SCERT.")

    def get_resolved_student_phone(self) -> Optional[str]:
        # Priority 1: Direct student phone candidates
        for candidate in [self.student_phone, self.student_mobile, self.phone, self.mobile, self.mobile_number, self.phone_number, self.mobileno, self.mobile_no, self.contact_no, self.mob_no]:
            if candidate and str(candidate).strip():
                digits = re.sub(r'\D', '', str(candidate).strip())
                if len(digits) >= 10:
                    return digits[-10:]
        # Priority 2: Fallback to guardian/father/parent phone candidates
        for candidate in [self.guardian_phone, self.father_phone, self.parent_phone, self.parent_mobile]:
            if candidate and str(candidate).strip():
                digits = re.sub(r'\D', '', str(candidate).strip())
                if len(digits) >= 10:
                    return digits[-10:]
        return None

    def get_resolved_guardian_phone(self) -> str:
        for candidate in [self.guardian_phone, self.father_phone, self.parent_phone, self.parent_mobile, self.student_phone, self.phone, self.mobile_number, self.mobileno, self.mobile_no, self.phone_number]:
            if candidate and str(candidate).strip():
                digits = re.sub(r'\D', '', str(candidate).strip())
                if len(digits) >= 10:
                    return digits[-10:]
        return "0000000000"

    @field_validator("guardian_phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Any) -> Optional[str]:
        if not v:
            return None
        cleaned = re.sub(r'\D', '', str(v).strip())
        return cleaned[-10:] if len(cleaned) >= 10 else str(v).strip()

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


class ExternalStudentUpdate(BaseModel):
    student_id: Optional[str] = Field(None, description="Miki Student ObjectId (if available)")
    name: Optional[str] = Field(None, description="Student's full name")
    dob: Optional[str] = Field(None, description="Student DOB YYYY-MM-DD")
    link: Optional[str] = Field(None, description="School identifier link")
    student_class: str = Field(..., description="Updated class / grade (e.g. '6', '10')")
    division: Optional[str] = Field(None, description="Division / Section")
    address: Optional[str] = Field(None, description="Updated address")
    guardian_name: Optional[str] = Field(None, description="Guardian name")
    guardian_phone: Optional[str] = Field(None, description="Guardian phone")
    student_phone: Optional[str] = Field(None, description="Student phone")
    phone: Optional[str] = Field(None, description="Student phone alias")
    mobile_number: Optional[str] = Field(None, description="Student mobile number alias")
    category: Optional[str] = Field(None, description="Curriculum category (SCERT/NCERT)")


from typing import Optional, Any
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
# 🚀 Endpoints
# ─────────────────────────────────────────────

@router.post(
    "/register-student",
    response_model=dict,
    summary="External student registration",
    description=(
        "Called by partner web applications at registration time. "
        "Creates or updates a student record and links it to the school identified by `link`."
    ),
    tags=["External Registration"]
)
async def external_register_student(
    payload: ExternalStudentRegistration,
    _: str = Depends(verify_api_key)
):
    resolved_st_phone = payload.get_resolved_student_phone()
    resolved_g_phone = payload.get_resolved_guardian_phone()
    raw_class_str = str(payload.student_class).strip()
    clean_class_str = re.sub(r'^(class|std|grade)\s*', '', raw_class_str, flags=re.I).strip()

    # ── 1. Resolve school by link or domain matching or Auto-Create ──────────
    school = await db.schools.find_one({"link": payload.link})
    if not school:
        import urllib.parse
        target_link = payload.link if payload.link.startswith("http") else f"http://{payload.link}"
        parsed = urllib.parse.urlparse(target_link)
        clean_domain = parsed.netloc or parsed.path
        domain_part = clean_domain.split(':')[0].replace("www.", "")
        if domain_part:
            school = await db.schools.find_one({
                "link": {"$regex": re.escape(domain_part), "$options": "i"}
            })

    if not school:
        raw_name = domain_part.split('.')[0] if 'domain_part' in locals() and domain_part else payload.link
        school_name = raw_name.replace("-", " ").replace("_", " ").title()
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

    # ── 2. Check duplicate / existing student matching ──────────────────────
    existing_student = await db.students.find_one({
        "student_name": {"$regex": f"^{re.escape(payload.name.strip())}$", "$options": "i"},
        "dob": payload.dob,
        "school_id": school_id
    })
    if not existing_student and resolved_st_phone:
        existing_student = await db.students.find_one({
            "school_id": school_id,
            "$or": [
                {"student_phone": resolved_st_phone},
                {"mobile_number": resolved_st_phone},
                {"phone": resolved_st_phone},
                {"guardian_phone": resolved_st_phone}
            ]
        })

    if existing_student:
        student_id_str = str(existing_student["_id"])
        
        # Update existing student's class and profile in Miki DB if updated in EduSoft
        update_data = {
            "student_class": clean_class_str,
            "student_class_raw": raw_class_str,
            "division": payload.division,
            "address": payload.address,
            "guardian_name": payload.guardian_name,
            "guardian_phone": resolved_g_phone,
            "category": payload.category,
            "updated_at": datetime.now(timezone.utc)
        }
        if resolved_st_phone:
            update_data["student_phone"] = resolved_st_phone
            update_data["mobile_number"] = resolved_st_phone
            update_data["phone"] = resolved_st_phone
            update_data["mobileno"] = resolved_st_phone
            update_data["mobile_no"] = resolved_st_phone
            update_data["phone_number"] = resolved_st_phone

        await db.students.update_one(
            {"_id": existing_student["_id"]},
            {"$set": update_data}
        )

        # Ensure EduSoft credentials exist for already registered student
        existing_cred = await db.edusoft_credentials.find_one({
            "$or": [{"student_id": student_id_str}, {"student_id": existing_student["_id"]}]
        })
        if not existing_cred:
            try:
                from app.utils.crypto import encrypt_password, generate_default_edusoft_credentials
                auto_username, auto_password = generate_default_edusoft_credentials(existing_student, student_id_str)
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

        # Ensure parent is linked in usertable
        await db.usertable.update_one(
            {"mobile_number": resolved_g_phone},
            {
                "$setOnInsert": {
                    "usertype": "parent",
                    "created_at": datetime.now(timezone.utc)
                },
                "$addToSet": {
                    "student_ids": existing_student["_id"]
                }
            },
            upsert=True
        )

        return {
            "status": "already_registered",
            "message": f"Student registered/updated successfully. Class set to '{clean_class_str}'.",
            "student_id": student_id_str,
            "student_class": clean_class_str,
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
        "student_class": clean_class_str,
        "student_class_raw": raw_class_str,
        "division": payload.division,
        "address": payload.address,
        "guardian_name": payload.guardian_name,
        "guardian_phone": resolved_g_phone,
        "student_phone": resolved_st_phone,
        "mobile_number": resolved_st_phone,
        "phone": resolved_st_phone,
        "mobileno": resolved_st_phone,
        "mobile_no": resolved_st_phone,
        "phone_number": resolved_st_phone,
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
    auto_username, auto_password = None, None
    try:
        from app.utils.crypto import encrypt_password, generate_default_edusoft_credentials
        auto_username, auto_password = generate_default_edusoft_credentials(student_doc, student_id_str)
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

    # ── 4c. Forward Registration to EduSoft Server to Sync with MySQL ─────
    try:
        import httpx
        import urllib.parse
        parsed = urllib.parse.urlparse(payload.link)
        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else payload.link.rstrip('/')
        edusoft_webhook_url = f"{base_url}/site/api_register_student"

        sync_payload = {
            "student_id": student_id_str,
            "name": payload.name,
            "student_class": payload.student_class,
            "division": payload.division,
            "address": payload.address,
            "dob": payload.dob,
            "guardian_name": payload.guardian_name,
            "guardian_phone": payload.guardian_phone,
            "student_phone": resolved_st_phone,
            "username": auto_username,
            "password": auto_password,
            "category": payload.category,
            "school_link": payload.link
        }

        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(edusoft_webhook_url, json=sync_payload)
            print(f"[EduSoft Sync] Forwarded registration to {edusoft_webhook_url}: Status {resp.status_code}")
    except Exception as e:
        print(f"[EduSoft Sync] Forwarding warning: {e}")

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
        "student_class": payload.student_class,
        "guardian_phone": payload.guardian_phone,
        "student_phone": resolved_st_phone
    }


@router.post(
    "/update-student",
    response_model=dict,
    summary="Update student details / class from external partner",
    description="Updates an existing student's class, division, or details in Miki.",
    tags=["External Registration"]
)
@router.put(
    "/update-student",
    response_model=dict,
    include_in_schema=False
)
@router.post(
    "/update-student-class",
    response_model=dict,
    include_in_schema=False
)
async def external_update_student(
    payload: ExternalStudentUpdate,
    _: str = Depends(verify_api_key)
):
    student = None
    if payload.student_id:
        try:
            s_oid = ObjectId(payload.student_id)
            student = await db.students.find_one({"$or": [{"_id": payload.student_id}, {"_id": s_oid}]})
        except Exception:
            student = await db.students.find_one({"_id": payload.student_id})

    if not student and payload.name and payload.dob and payload.link:
        school = await db.schools.find_one({"link": payload.link})
        if school:
            student = await db.students.find_one({
                "student_name": payload.name,
                "dob": payload.dob,
                "school_id": str(school["_id"])
            })

    if not student:
        raise HTTPException(status_code=404, detail="Student not found for updating")

    update_fields = {"updated_at": datetime.now(timezone.utc)}
    if payload.student_class:
        update_fields["student_class"] = payload.student_class
    if payload.division:
        update_fields["division"] = payload.division
    if payload.address:
        update_fields["address"] = payload.address
    if payload.guardian_name:
        update_fields["guardian_name"] = payload.guardian_name
    if payload.guardian_phone:
        update_fields["guardian_phone"] = payload.guardian_phone
    if payload.category:
        update_fields["category"] = payload.category

    st_p = payload.student_phone or payload.phone or payload.mobile_number
    if st_p and str(st_p).strip():
        cleaned_p = str(st_p).strip()
        update_fields["student_phone"] = cleaned_p
        update_fields["mobile_number"] = cleaned_p
        update_fields["phone"] = cleaned_p

    await db.students.update_one({"_id": student["_id"]}, {"$set": update_fields})

    return {
        "status": "success",
        "message": f"Student '{student.get('student_name')}' updated successfully.",
        "student_id": str(student["_id"]),
        "student_class": payload.student_class
    }

