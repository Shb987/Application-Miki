import os
import io
import uuid
from typing import List, Optional, Union
from datetime import datetime, timezone
from bson import ObjectId
from PIL import Image
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, status
from fastapi.encoders import jsonable_encoder

from app.core.database import db
from app.models.doctor_models import (
    DoctorCreate,
    DoctorUpdate,
    DoctorStatusUpdate,
    DoctorResponse,
    DoctorPublicResponse,
    SPECIALIZATION_OPTIONS
)
from app.utils.admin_auth import require_permission, log_admin_activity

# ─── Directories ─────────────────────────────────────────────────────────────
UPLOAD_DIR = os.path.join("app", "static", "uploads", "doctors")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ─── Routers ─────────────────────────────────────────────────────────────────
admin_router = APIRouter(prefix="/miki-care", tags=["Miki Care - Admin"])
public_router = APIRouter(prefix="/miki-care", tags=["Miki Care - Public"])


# ─── Helper Functions ────────────────────────────────────────────────────────
def serialize_doctor(doc: dict) -> dict:
    """Standardizes doctor document for responses."""
    if not doc:
        return {}
    doc = dict(doc)
    doc_id = str(doc.pop("_id", ""))
    doc["id"] = doc_id
    if not doc.get("doctor_id"):
        doc["doctor_id"] = doc_id

    # Handle image URL aliasing
    profile_img = doc.get("profile_image")
    doc["profile_image_url"] = profile_img

    # Ensure list fields
    if not isinstance(doc.get("available_days"), list):
        doc["available_days"] = []

    # Ensure status consistency
    is_active = doc.get("is_active", True)
    if "status" not in doc or not doc["status"]:
        doc["status"] = "Active" if is_active else "Inactive"
    else:
        doc["is_active"] = str(doc["status"]).strip().lower() == "active"

    return doc


def generate_unique_doctor_id() -> str:
    """Generates a clean, unique human-friendly Doctor ID (e.g. DOC-A1B2C3D4)."""
    random_hex = uuid.uuid4().hex[:8].upper()
    return f"DOC-{random_hex}"


def save_and_optimize_image(file_obj, filepath: str, max_dim: int = 1200) -> None:
    """
    Validates, resizes and optimizes doctor profile photos.
    Preserves transparency for PNG/WebP while compressing JPEG.
    """
    file_bytes = file_obj.file.read()
    file_obj.file.seek(0)
    img = Image.open(io.BytesIO(file_bytes))

    # Resize if larger than max_dim
    w, h = img.size
    if w > max_dim or h > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    ext = os.path.splitext(filepath)[1].lower()
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)

    if ext in (".jpg", ".jpeg"):
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(filepath, "JPEG", quality=85, optimize=True)
    elif ext == ".png":
        if has_alpha and img.mode != "RGBA":
            img = img.convert("RGBA")
        elif not has_alpha and img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        img.save(filepath, "PNG", optimize=True)
    elif ext == ".webp":
        if has_alpha and img.mode != "RGBA":
            img = img.convert("RGBA")
        img.save(filepath, "WEBP", quality=85)
    else:
        img.save(filepath)


# ═════════════════════════════════════════════════════════════════════════════
# 🏥 ADMIN PANEL APIS
# ═════════════════════════════════════════════════════════════════════════════

@admin_router.post("/upload-image")
async def upload_doctor_image(
    file: UploadFile = File(...),
    current_admin: dict = Depends(require_permission("Miki Care", "create"))
):
    """
    Upload and validate doctor's profile image.
    Supports JPG, JPEG, PNG, WEBP (Max 5MB).
    """
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Only JPG, JPEG, PNG, and WebP are allowed."
        )

    # Validate Content-Type
    content_type = (file.content_type or "").lower()
    if not (content_type.startswith("image/") or ext in allowed_extensions):
        raise HTTPException(status_code=400, detail="Invalid image file.")

    # Validate File Size (5MB limit)
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    max_size = 5 * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(status_code=400, detail="Image size exceeds maximum limit of 5MB.")

    # Unique filename
    safe_name = f"doc_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}{ext}"
    filepath = os.path.join(UPLOAD_DIR, safe_name)

    try:
        save_and_optimize_image(file, filepath)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process and save image: {str(e)}")

    relative_url = f"/uploads/doctors/{safe_name}"
    return {
        "status": "success",
        "message": "Doctor profile image uploaded successfully",
        "url": relative_url
    }


@admin_router.post("/doctors", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_doctor(
    doctor: DoctorCreate,
    current_admin: dict = Depends(require_permission("Miki Care", "create"))
):
    """
    Add a new doctor profile (Admin only).
    Generates unique doctor ID and timestamps.
    """
    doc_dict = doctor.model_dump()

    # Validation
    if not doc_dict.get("doctor_name", "").strip():
        raise HTTPException(status_code=400, detail="Doctor name is required.")

    if not doc_dict.get("qualification", "").strip():
        raise HTTPException(status_code=400, detail="Doctor qualification is required.")

    if doc_dict.get("specialization") == "Other" and not doc_dict.get("other_specialization", "").strip():
        raise HTTPException(status_code=400, detail="Please specify the 'Other Specialization'.")

    # Generate unique doctor ID
    while True:
        candidate_id = generate_unique_doctor_id()
        existing = await db.doctors.find_one({"doctor_id": candidate_id})
        if not existing:
            doc_dict["doctor_id"] = candidate_id
            break

    # Sync status and is_active
    status_str = doc_dict.get("status", "Active").capitalize()
    doc_dict["status"] = status_str
    doc_dict["is_active"] = (status_str == "Active")

    now = datetime.now(timezone.utc)
    doc_dict["created_at"] = now
    doc_dict["updated_at"] = now

    result = await db.doctors.insert_one(doc_dict)
    new_id = str(result.inserted_id)

    await log_admin_activity(
        username=current_admin.get("sub", "admin"),
        role=current_admin.get("role", "admin"),
        action="create_doctor",
        details=f"Created doctor '{doctor.doctor_name}' (ID: {doc_dict['doctor_id']}) with specialization '{doctor.specialization}'",
        status="success"
    )

    return {
        "status": "success",
        "message": "Doctor profile created successfully",
        "id": new_id,
        "doctor_id": doc_dict["doctor_id"]
    }


@admin_router.get("/doctors", response_model=dict)
async def list_doctors(
    search: Optional[str] = Query(None, description="Search by name, qualification, hospital, or city"),
    specialization: Optional[str] = Query(None, description="Filter by doctor specialization"),
    status: Optional[str] = Query(None, description="Filter by status: Active, Inactive, or All"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    current_admin: dict = Depends(require_permission("Miki Care", "read"))
):
    """
    List all doctors with search, filtering, and pagination (Admin only).
    """
    query = {}

    # Status filter
    if status and status.lower() != "all":
        if status.lower() == "active":
            query["is_active"] = True
        elif status.lower() == "inactive":
            query["is_active"] = False

    # Specialization filter
    if specialization and specialization.lower() != "all":
        query["specialization"] = specialization

    # Search filter
    if search and search.strip():
        term = search.strip()
        query["$or"] = [
            {"doctor_name": {"$regex": term, "$options": "i"}},
            {"doctor_id": {"$regex": term, "$options": "i"}},
            {"qualification": {"$regex": term, "$options": "i"}},
            {"hospital_clinic_name": {"$regex": term, "$options": "i"}},
            {"city": {"$regex": term, "$options": "i"}},
            {"other_specialization": {"$regex": term, "$options": "i"}},
        ]

    total = await db.doctors.count_documents(query)
    skip = (page - 1) * limit
    cursor = db.doctors.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)

    # Statistics for dashboard KPI
    active_count = await db.doctors.count_documents({"is_active": True})
    inactive_count = await db.doctors.count_documents({"is_active": False})
    total_all = await db.doctors.count_documents({})

    serialized = [serialize_doctor(d) for d in docs]
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "status": "success",
        "data": serialized,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "stats": {
            "total_all": total_all,
            "active_count": active_count,
            "inactive_count": inactive_count
        }
    }


@admin_router.get("/doctors/{doctor_id}", response_model=dict)
async def get_doctor_details(
    doctor_id: str,
    current_admin: dict = Depends(require_permission("Miki Care", "read"))
):
    """
    Retrieve single doctor details by doctor_id or MongoDB ObjectId.
    """
    query = {"$or": [{"doctor_id": doctor_id}]}
    if ObjectId.is_valid(doctor_id):
        query["$or"].append({"_id": ObjectId(doctor_id)})

    doctor = await db.doctors.find_one(query)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")

    return {
        "status": "success",
        "data": serialize_doctor(doctor)
    }


@admin_router.put("/doctors/{doctor_id}", response_model=dict)
async def update_doctor(
    doctor_id: str,
    doctor_update: DoctorUpdate,
    current_admin: dict = Depends(require_permission("Miki Care", "update"))
):
    """
    Update an existing doctor profile (Admin only).
    """
    query = {"$or": [{"doctor_id": doctor_id}]}
    if ObjectId.is_valid(doctor_id):
        query["$or"].append({"_id": ObjectId(doctor_id)})

    existing = await db.doctors.find_one(query)
    if not existing:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")

    update_dict = doctor_update.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields provided to update.")

    # Validation if fields provided
    if "doctor_name" in update_dict and not update_dict["doctor_name"].strip():
        raise HTTPException(status_code=400, detail="Doctor name cannot be empty.")

    if "specialization" in update_dict and update_dict["specialization"] == "Other":
        other_spec = update_dict.get("other_specialization") or existing.get("other_specialization", "")
        if not other_spec.strip():
            raise HTTPException(status_code=400, detail="Please specify the 'Other Specialization'.")

    # Status / is_active syncing
    if "status" in update_dict:
        status_str = update_dict["status"].capitalize()
        update_dict["status"] = status_str
        update_dict["is_active"] = (status_str == "Active")
    elif "is_active" in update_dict:
        update_dict["status"] = "Active" if update_dict["is_active"] else "Inactive"

    update_dict["updated_at"] = datetime.now(timezone.utc)

    await db.doctors.update_one({"_id": existing["_id"]}, {"$set": update_dict})

    await log_admin_activity(
        username=current_admin.get("sub", "admin"),
        role=current_admin.get("role", "admin"),
        action="update_doctor",
        details=f"Updated doctor profile '{existing.get('doctor_name')}' (ID: {existing.get('doctor_id')})",
        status="success"
    )

    return {
        "status": "success",
        "message": "Doctor profile updated successfully"
    }


@admin_router.patch("/doctors/{doctor_id}/status", response_model=dict)
async def toggle_doctor_status(
    doctor_id: str,
    status_data: DoctorStatusUpdate,
    current_admin: dict = Depends(require_permission("Miki Care", "update"))
):
    """
    Quick activate or deactivate doctor profile.
    """
    query = {"$or": [{"doctor_id": doctor_id}]}
    if ObjectId.is_valid(doctor_id):
        query["$or"].append({"_id": ObjectId(doctor_id)})

    existing = await db.doctors.find_one(query)
    if not existing:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")

    if status_data.status is not None:
        new_status = status_data.status.capitalize()
        new_is_active = (new_status == "Active")
    elif status_data.is_active is not None:
        new_is_active = bool(status_data.is_active)
        new_status = "Active" if new_is_active else "Inactive"
    else:
        # Toggle current
        curr_active = existing.get("is_active", True)
        new_is_active = not curr_active
        new_status = "Active" if new_is_active else "Inactive"

    update_fields = {
        "status": new_status,
        "is_active": new_is_active,
        "updated_at": datetime.now(timezone.utc)
    }

    await db.doctors.update_one({"_id": existing["_id"]}, {"$set": update_fields})

    await log_admin_activity(
        username=current_admin.get("sub", "admin"),
        role=current_admin.get("role", "admin"),
        action="update_doctor_status",
        details=f"Changed doctor status for '{existing.get('doctor_name')}' to {new_status}",
        status="success"
    )

    return {
        "status": "success",
        "message": f"Doctor profile is now {new_status}",
        "status_value": new_status,
        "is_active": new_is_active
    }


@admin_router.delete("/doctors/{doctor_id}", response_model=dict)
async def delete_doctor(
    doctor_id: str,
    current_admin: dict = Depends(require_permission("Miki Care", "delete"))
):
    """
    Delete doctor profile record (Admin only).
    """
    query = {"$or": [{"doctor_id": doctor_id}]}
    if ObjectId.is_valid(doctor_id):
        query["$or"].append({"_id": ObjectId(doctor_id)})

    existing = await db.doctors.find_one(query)
    if not existing:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")

    # Remove stored image file if exists
    profile_img = existing.get("profile_image")
    if profile_img and profile_img.startswith("/uploads/doctors/"):
        filename = profile_img.replace("/uploads/doctors/", "")
        local_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

    await db.doctors.delete_one({"_id": existing["_id"]})

    await log_admin_activity(
        username=current_admin.get("sub", "admin"),
        role=current_admin.get("role", "admin"),
        action="delete_doctor",
        details=f"Deleted doctor profile '{existing.get('doctor_name')}' (ID: {existing.get('doctor_id')})",
        status="success"
    )

    return {
        "status": "success",
        "message": "Doctor profile deleted successfully"
    }


# ═════════════════════════════════════════════════════════════════════════════
# 👨‍👩‍👧 PARENTS AND STUDENTS GET API (NO PARAMETERS)
# ═════════════════════════════════════════════════════════════════════════════

@public_router.get("/doctors", response_model=List[DoctorPublicResponse])
async def get_doctors_for_parents_and_students():
    """
    GET API for Parents and Students:
    Endpoint: GET /api/v1/miki-care/doctors

    - No parameters needed.
    - Returns all ACTIVE doctor profiles added through Miki Care admin panel.
    - Excludes inactive doctor profiles.
    - Fetches the latest saved details directly from the database.
    - Returns doctor ID, doctor name, profile image URL, specialization,
      qualification, experience, hospital/clinic name, consultation address,
      city, state, available days, available time, short biography,
      contact number, and email.
    """
    query = {
        "$or": [
            {"is_active": True},
            {"status": {"$regex": "^active$", "$options": "i"}}
        ]
    }

    cursor = db.doctors.find(query).sort([("experience", -1), ("created_at", -1)])
    docs = await cursor.to_list(length=None)

    results = []
    for d in docs:
        serialized = serialize_doctor(d)
        
        # Display resolved specialization if 'Other'
        spec_display = serialized.get("specialization") or "Specialist"
        if spec_display == "Other" and serialized.get("other_specialization"):
            spec_display = serialized["other_specialization"]

        results.append(
            DoctorPublicResponse(
                doctor_id=serialized.get("doctor_id") or serialized.get("id"),
                doctor_name=serialized.get("doctor_name", ""),
                profile_image=serialized.get("profile_image"),
                profile_image_url=serialized.get("profile_image"),
                specialization=spec_display,
                other_specialization=serialized.get("other_specialization"),
                qualification=serialized.get("qualification", ""),
                experience=float(serialized.get("experience") or 0.0),
                hospital_clinic_name=serialized.get("hospital_clinic_name"),
                consultation_address=serialized.get("consultation_address"),
                city=serialized.get("city"),
                state=serialized.get("state"),
                available_days=serialized.get("available_days") or [],
                available_time=serialized.get("available_time"),
                short_biography=serialized.get("short_biography"),
                contact_number=serialized.get("contact_number"),
                email=serialized.get("email"),
                status=serialized.get("status", "Active"),
                is_active=True
            )
        )

    return results

