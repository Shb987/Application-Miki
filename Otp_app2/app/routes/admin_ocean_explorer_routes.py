import os
import shutil
import io
from typing import List
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from PIL import Image

from app.core.database import db
from app.models.explorer_models import OceanExplorerCreate, OceanExplorerUpdate, OceanExplorerResponse
from app.utils.admin_auth import require_permission

router = APIRouter(prefix="/ocean-explorer", tags=["Ocean Explorer - Admin"])

UPLOAD_DIR = os.path.join("app", "static", "uploads", "ocean")
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

def save_and_optimize_image(file_obj, filepath: str, max_dim: int = 1920):
    """Saves uploaded image, automatically resizing & compressing to optimize load times while preserving PNG transparency."""
    try:
        file_bytes = file_obj.file.read()
        file_obj.file.seek(0)
        img = Image.open(io.BytesIO(file_bytes))

        w, h = img.size
        if w > max_dim or h > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        ext = os.path.splitext(filepath)[1].lower()

        # Check for transparency (RGBA, LA, or Palette with transparency)
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)

        if ext == ".png":
            if has_alpha:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
            else:
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
            img.save(filepath, format="PNG", optimize=True)
        elif ext == ".webp":
            if has_alpha and img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(filepath, format="WEBP", quality=85, optimize=True)
        elif ext in [".jpg", ".jpeg"]:
            if has_alpha:
                # Composite transparent background over clean WHITE instead of default BLACK
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.save(filepath, format="JPEG", quality=85, optimize=True)
        else:
            with open(filepath, "wb") as buffer:
                shutil.copyfileobj(file_obj.file, buffer)
    except Exception as e:
        print(f"[WARN] Error in save_and_optimize_image: {e}")
        file_obj.file.seek(0)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file_obj.file, buffer)

@router.get("", response_model=List[OceanExplorerResponse])
async def get_all_ocean_entities(current_admin: dict = Depends(require_permission("Ocean Explorer", "read"))):
    """Retrieve all Ocean Explorer entities ordered by order number (Requires Admin Authentication)"""
    cursor = db.ocean_explorer.find().sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]

@router.post("", response_model=OceanExplorerResponse)
async def create_ocean_entity(data: OceanExplorerCreate, current_admin: dict = Depends(require_permission("Ocean Explorer", "create"))):
    """Create a new Ocean Explorer entity (Requires Admin Authentication)"""
    existing = await db.ocean_explorer.find_one({"name": {"$regex": f"^{data.name.strip()}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail=f"Ocean entity '{data.name}' already exists.")

    new_doc = data.model_dump()
    new_doc["created_at"] = datetime.now(timezone.utc)
    new_doc["updated_at"] = datetime.now(timezone.utc)

    result = await db.ocean_explorer.insert_one(new_doc)
    created = await db.ocean_explorer.find_one({"_id": result.inserted_id})
    return serialize_doc(created)

# --- STATIC SPECIFIC ROUTES (MUST be defined before dynamic /{item_id} routes) ---

@router.get("/uploaded-images")
async def get_uploaded_ocean_images(current_admin: dict = Depends(require_permission("Ocean Explorer", "read"))):
    """List all uploaded images stored in ocean uploads directory with size metadata."""
    if not os.path.exists(UPLOAD_DIR):
        return []

    items = []
    for filename in os.listdir(UPLOAD_DIR):
        filepath = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(filepath):
            stat = os.stat(filepath)
            size_bytes = stat.st_size
            if size_bytes > 1024 * 1024:
                size_formatted = f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                size_formatted = f"{size_bytes / 1024:.0f} KB"

            items.append({
                "filename": filename,
                "url": f"/uploads/ocean/{filename}",
                "size_bytes": size_bytes,
                "size_formatted": size_formatted,
                "mtime": stat.st_mtime
            })

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items

@router.delete("/uploaded-images/{filename}")
async def delete_uploaded_ocean_image(filename: str, current_admin: dict = Depends(require_permission("Ocean Explorer", "delete"))):
    """Delete a specific uploaded image file from server disk."""
    safe_name = os.path.basename(filename)
    filepath = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        os.remove(filepath)
        return {"message": f"Deleted {safe_name} successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@router.post("/upload-image")
async def upload_ocean_image(file: UploadFile = File(...), current_admin: dict = Depends(require_permission("Ocean Explorer", "create"))):
    """Upload a single image file for ocean feature image or cover image (Requires Admin Authentication)"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image format (JPEG, PNG, WEBP, SVG)")

    ext = os.path.splitext(file.filename)[1] or ".png"
    filename = f"ocean_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    save_and_optimize_image(file, filepath)

    relative_url = f"/uploads/ocean/{filename}"
    return {"message": "Image uploaded successfully", "url": relative_url}

@router.post("/upload-multiple-images")
async def upload_multiple_ocean_images(files: List[UploadFile] = File(...), current_admin: dict = Depends(require_permission("Ocean Explorer", "create"))):
    """Upload multiple image files for ocean gallery (Requires Admin Authentication)"""
    uploaded_urls = []
    for file in files:
        if file.content_type.startswith("image/"):
            ext = os.path.splitext(file.filename)[1] or ".png"
            filename = f"ocean_gal_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
            filepath = os.path.join(UPLOAD_DIR, filename)

            save_and_optimize_image(file, filepath)

            uploaded_urls.append(f"/uploads/ocean/{filename}")

    return {"message": f"{len(uploaded_urls)} images uploaded successfully", "urls": uploaded_urls}

# --- DYNAMIC PARAMETER ROUTES (defined after specific static routes) ---

@router.get("/{item_id}", response_model=OceanExplorerResponse)
async def get_ocean_entity(item_id: str, current_admin: dict = Depends(require_permission("Ocean Explorer", "read"))):
    """Get single Ocean Explorer entity by ID (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    doc = await db.ocean_explorer.find_one({"_id": ObjectId(item_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Ocean entity not found")

    return serialize_doc(doc)

@router.put("/{item_id}", response_model=OceanExplorerResponse)
async def update_ocean_entity(item_id: str, update_data: OceanExplorerUpdate, current_admin: dict = Depends(require_permission("Ocean Explorer", "update"))):
    """Update an existing Ocean Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    fields = {k: v for k, v in update_data.model_dump(exclude_unset=True).items()}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    fields["updated_at"] = datetime.now(timezone.utc)

    result = await db.ocean_explorer.update_one(
        {"_id": ObjectId(item_id)},
        {"$set": fields}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ocean entity not found")

    updated = await db.ocean_explorer.find_one({"_id": ObjectId(item_id)})
    return serialize_doc(updated)

@router.delete("/{item_id}")
async def delete_ocean_entity(item_id: str, current_admin: dict = Depends(require_permission("Ocean Explorer", "delete"))):
    """Delete an Ocean Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.ocean_explorer.delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ocean entity not found")

    return {"message": "Ocean entity deleted successfully", "id": item_id}
