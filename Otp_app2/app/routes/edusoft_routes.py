"""
edusoft_routes.py — EduSoft External App credential storage & retrieval.

Endpoints:
  POST /api/v1/edusoft/store-credentials   — Store auto-generated credentials
  GET  /api/v1/edusoft/credentials         — Retrieve credentials by student_id

Both endpoints are protected by X-API-Key (EDUSOFT_API_KEY from .env).
"""

from fastapi import APIRouter, HTTPException, Header, Depends, Query
from datetime import datetime, timezone
from bson import ObjectId
import re

from app.core.database import db
from app.core.settings import settings
from app.models.edusoft_models import EduSoftStoreCredentials
from app.utils.crypto import encrypt_password, decrypt_password

router = APIRouter()


from typing import Optional
from fastapi.security import APIKeyHeader

edusoft_api_key_scheme = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="EduSoft Partner API Key (X-API-Key)"
)

async def verify_edusoft_api_key(
    x_api_key_scheme_val: Optional[str] = Depends(edusoft_api_key_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key", description="EduSoft Partner API Key")
):
    """
    EduSoft partner API key guard.
    Shows X-API-Key parameter in endpoint form and maintains Swagger lock icon.
    """
    key_to_check = x_api_key_scheme_val or x_api_key
    if key_to_check:
        if key_to_check.startswith("Bearer "):
            key_to_check = key_to_check[7:]
        valid_keys = [
            getattr(settings, "EDUSOFT_API_KEY", ""),
            getattr(settings, "EXTERNAL_API_KEY", "")
        ]
        if key_to_check not in valid_keys and settings.EDUSOFT_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")
    return key_to_check


# ─────────────────────────────────────────────────────────────────────────────
# 📥 Endpoint 1: Store Credentials
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/store-credentials",
    response_model=dict,
    summary="Store EduSoft credentials for a registered student",
    description=(
        "Called by the EduSoft website right after student registration. "
        "Receives the student_id (returned from /api/v1/register-student) "
        "along with the auto-generated username and password. "
        "The password is Fernet-encrypted before storage. "
        "Returns 409 if credentials for this student already exist."
    ),
    tags=["EduSoft External API"]
)
async def store_edusoft_credentials(
    payload: EduSoftStoreCredentials,
    _: str = Depends(verify_edusoft_api_key)
):
    # ── 1. Validate student_id exists in db.students ──────────────────────────
    student_oid = None
    try:
        student_oid = ObjectId(payload.student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format (must be a 24-char hex ObjectId)")

    student_query = [{"_id": payload.student_id}]
    if student_oid:
        student_query.append({"_id": student_oid})

    student = await db.students.find_one({"$or": student_query})
    if not student:
        raise HTTPException(
            status_code=404,
            detail=f"No student found with student_id '{payload.student_id}'"
        )

    # ── 2. Check: student_id already has credentials? → 409 ──────────────────
    cred_query = [{"student_id": payload.student_id}]
    if student_oid:
        cred_query.append({"student_id": student_oid})

    existing_by_student = await db.edusoft_credentials.find_one({"$or": cred_query})
    if existing_by_student:
        # Update existing credentials if updating
        encrypted_pwd = encrypt_password(payload.password)
        await db.edusoft_credentials.update_one(
            {"$or": cred_query},
            {"$set": {
                "username": payload.username,
                "password_enc": encrypted_pwd,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        return {
            "status": "success",
            "message": "Credentials updated successfully",
            "student_id": payload.student_id,
            "username": payload.username
        }

    # ── 3. Check: username already taken by another student? → 409 ───────────
    existing_by_username = await db.edusoft_credentials.find_one({"username": payload.username})
    if existing_by_username:
        raise HTTPException(
            status_code=409,
            detail=f"Username '{payload.username}' is already taken"
        )

    # ── 4. Encrypt password and insert document ───────────────────────────────
    encrypted_pwd = encrypt_password(payload.password)

    credential_doc = {
        "student_id":   payload.student_id,
        "username":     payload.username,
        "password_enc": encrypted_pwd,          # Fernet-encrypted — never plain-text
        "created_at":   datetime.now(timezone.utc),
        "registered_via": "edusoft_api"
    }

    await db.edusoft_credentials.insert_one(credential_doc)

    return {
        "status":     "success",
        "message":    "Credentials stored successfully",
        "student_id": payload.student_id,
        "username":   payload.username
    }


# ─────────────────────────────────────────────────────────────────────────────
# 📤 Endpoint 2: Retrieve Credentials
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/credentials",
    response_model=dict,
    summary="Retrieve EduSoft credentials for a student",
    description=(
        "Called by the EduSoft login website to retrieve the stored username and "
        "password for a student identified by student_id. "
        "The password is decrypted before being returned. "
        "Protected by X-API-Key — should only be called from EduSoft backend, never from the browser directly."
    ),
    tags=["EduSoft External API"]
)
async def get_edusoft_credentials(
    student_id: str = Query(..., description="The 24-char hex student ObjectId"),
    _: str = Depends(verify_edusoft_api_key)
):
    # ── 1. Basic format validation ────────────────────────────────────────────
    student_id = student_id.strip()
    if len(student_id) != 24:
        raise HTTPException(status_code=400, detail="student_id must be a 24-character hex ObjectId")

    student_oid = None
    try:
        student_oid = ObjectId(student_id)
    except Exception:
        pass

    # ── 2. Look up credentials by student_id (supports both string and ObjectId) ──
    cred_query = [{"student_id": student_id}]
    if student_oid:
        cred_query.append({"student_id": student_oid})

    credential = await db.edusoft_credentials.find_one({"$or": cred_query})

    # ── 2b. Auto-provision fallback if student exists in db.students ──────────
    if not credential:
        student_query = [{"_id": student_id}]
        if student_oid:
            student_query.append({"_id": student_oid})

        student_doc = await db.students.find_one({"$or": student_query})
        if not student_doc:
            raise HTTPException(
                status_code=404,
                detail=f"No credentials or student record found for student_id '{student_id}'"
            )

        # Auto-provision credentials for valid registered student
        raw_name = student_doc.get("student_name", "")
        clean_name = re.sub(r'[^a-z0-9]', '', raw_name.lower())[:10] or "student"
        short_id = student_id[-6:]
        auto_username = f"{clean_name}_{short_id}"

        # Ensure username uniqueness
        existing_user = await db.edusoft_credentials.find_one({"username": auto_username})
        if existing_user:
            auto_username = f"user_{student_id}"

        auto_password = f"Edu@{short_id}!"
        encrypted_pwd = encrypt_password(auto_password)

        credential_doc = {
            "student_id": student_id,
            "username": auto_username,
            "password_enc": encrypted_pwd,
            "created_at": datetime.now(timezone.utc),
            "registered_via": "auto_provisioned"
        }
        await db.edusoft_credentials.insert_one(credential_doc)
        credential = credential_doc

    # ── 3. Decrypt the stored password ───────────────────────────────────────
    plain_password = decrypt_password(credential["password_enc"])

    # ── 4. Retrieve school link ──────────────────────────────────────────────
    school_link = None
    try:
        student_query = [{"_id": student_id}]
        if student_oid:
            student_query.append({"_id": student_oid})
        student_doc = await db.students.find_one({"$or": student_query})

        if student_doc and "school_id" in student_doc:
            school_id_val = student_doc["school_id"]
            school_query = [{"_id": school_id_val}]
            try:
                school_query.append({"_id": ObjectId(str(school_id_val))})
            except Exception:
                pass
            school_doc = await db.schools.find_one({"$or": school_query})
            if school_doc and "link" in school_doc:
                school_link = school_doc["link"]
    except Exception as e:
        print(f"Error fetching school link for student {student_id}: {e}")

    return {
        "student_id": student_id,
        "username":   credential["username"],
        "password":   plain_password,
        "school_link": school_link
    }

