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

from app.core.database import db
from app.core.settings import settings
from app.models.edusoft_models import EduSoftStoreCredentials
from app.utils.crypto import encrypt_password, decrypt_password

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 🔑 API Key Guard
# ─────────────────────────────────────────────────────────────────────────────

async def verify_edusoft_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """
    EduSoft partner apps must include the header:
        X-API-Key: <value of EDUSOFT_API_KEY in .env>
    """
    if x_api_key != settings.EDUSOFT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing EduSoft API key")
    return x_api_key


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
    try:
        student_oid = ObjectId(payload.student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format (must be a 24-char hex ObjectId)")

    student = await db.students.find_one({"_id": student_oid})
    if not student:
        raise HTTPException(
            status_code=404,
            detail=f"No student found with student_id '{payload.student_id}'"
        )

    # ── 2. Check: student_id already has credentials? → 409 ──────────────────
    existing_by_student = await db.edusoft_credentials.find_one({"student_id": payload.student_id})
    if existing_by_student:
        raise HTTPException(
            status_code=409,
            detail="Student credentials already registered"
        )

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

    # ── 2. Look up credentials by student_id ─────────────────────────────────
    credential = await db.edusoft_credentials.find_one({"student_id": student_id})
    if not credential:
        raise HTTPException(
            status_code=404,
            detail=f"No credentials found for student_id '{student_id}'"
        )

    # ── 3. Decrypt the stored password ───────────────────────────────────────
    plain_password = decrypt_password(credential["password_enc"])

    return {
        "student_id": student_id,
        "username":   credential["username"],
        "password":   plain_password
    }
