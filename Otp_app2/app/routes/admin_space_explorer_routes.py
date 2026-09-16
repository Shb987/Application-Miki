import os
import shutil
from typing import List
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File

from app.core.database import db
from app.models.space_explorer_models import SpaceExplorerCreate, SpaceExplorerUpdate, SpaceExplorerResponse
from app.utils.admin_auth import get_current_admin

router = APIRouter(prefix="/space-explorer", tags=["Space Explorer - Admin"])

UPLOAD_DIR = os.path.join("app", "static", "uploads", "space")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def serialize_doc(doc):
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    if "gallery_images" not in doc or doc["gallery_images"] is None:
        doc["gallery_images"] = []
    if "descriptions" not in doc or doc["descriptions"] is None:
        doc["descriptions"] = [doc.get("full_description")] if doc.get("full_description") else []
    return doc

@router.get("", response_model=List[SpaceExplorerResponse])
async def get_all_space_entities(current_admin: dict = Depends(get_current_admin)):
    """Retrieve all Space Explorer entities ordered by order number (Requires Admin Authentication)"""
    cursor = db.space_explorer.find().sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]

@router.post("", response_model=SpaceExplorerResponse)
async def create_space_entity(data: SpaceExplorerCreate, current_admin: dict = Depends(get_current_admin)):
    """Create a new Space Explorer entity (Requires Admin Authentication)"""
    existing = await db.space_explorer.find_one({"name": {"$regex": f"^{data.name.strip()}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail=f"Space entity '{data.name}' already exists.")

    new_doc = data.model_dump()
    new_doc["created_at"] = datetime.now(timezone.utc)
    new_doc["updated_at"] = datetime.now(timezone.utc)

    result = await db.space_explorer.insert_one(new_doc)
    created = await db.space_explorer.find_one({"_id": result.inserted_id})
    return serialize_doc(created)

@router.get("/{item_id}", response_model=SpaceExplorerResponse)
async def get_space_entity(item_id: str, current_admin: dict = Depends(get_current_admin)):
    """Get single Space Explorer entity by ID (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    doc = await db.space_explorer.find_one({"_id": ObjectId(item_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Space entity not found")

    return serialize_doc(doc)

@router.put("/{item_id}", response_model=SpaceExplorerResponse)
async def update_space_entity(item_id: str, update_data: SpaceExplorerUpdate, current_admin: dict = Depends(get_current_admin)):
    """Update an existing Space Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    fields = {k: v for k, v in update_data.model_dump(exclude_unset=True).items()}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    fields["updated_at"] = datetime.now(timezone.utc)

    result = await db.space_explorer.update_one(
        {"_id": ObjectId(item_id)},
        {"$set": fields}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Space entity not found")

    updated = await db.space_explorer.find_one({"_id": ObjectId(item_id)})
    return serialize_doc(updated)

@router.delete("/{item_id}")
async def delete_space_entity(item_id: str, current_admin: dict = Depends(get_current_admin)):
    """Delete a Space Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.space_explorer.delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Space entity not found")

    return {"message": "Space entity deleted successfully", "id": item_id}

@router.post("/upload-image")
async def upload_space_image(file: UploadFile = File(...), current_admin: dict = Depends(get_current_admin)):
    """Upload a single image file for planet image or cover image (Requires Admin Authentication)"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image format (JPEG, PNG, WEBP, SVG)")

    ext = os.path.splitext(file.filename)[1] or ".png"
    filename = f"space_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    relative_url = f"/uploads/space/{filename}"
    return {"message": "Image uploaded successfully", "url": relative_url}

@router.post("/upload-multiple-images")
async def upload_multiple_space_images(files: List[UploadFile] = File(...), current_admin: dict = Depends(get_current_admin)):
    """Upload multiple image files for planet gallery (Requires Admin Authentication)"""
    uploaded_urls = []
    for file in files:
        if file.content_type.startswith("image/"):
            ext = os.path.splitext(file.filename)[1] or ".png"
            filename = f"space_gal_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
            filepath = os.path.join(UPLOAD_DIR, filename)

            with open(filepath, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            uploaded_urls.append(f"/uploads/space/{filename}")

    return {"message": f"{len(uploaded_urls)} images uploaded successfully", "urls": uploaded_urls}
