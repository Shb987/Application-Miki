import os
import shutil
import io
from typing import List
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from PIL import Image

from app.core.database import db
from app.models.explorer_models import IndianExplorerCreate, IndianExplorerUpdate, IndianExplorerResponse
from app.utils.admin_auth import require_permission

router = APIRouter(prefix="/indian-explorer", tags=["Indian Explorer - Admin"])

UPLOAD_DIR = os.path.join("app", "static", "uploads", "indian")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def serialize_doc(doc):
    if not doc:
        return None

    doc = dict(doc)
    doc["id"] = str(doc.pop("_id")) if "_id" in doc else doc.get("id", "")
    if "gallery_images" not in doc or doc["gallery_images"] is None:
        doc["gallery_images"] = []
    if "descriptions" not in doc or doc["descriptions"] is None:
        doc["descriptions"] = [doc.get("full_description")] if doc.get("full_description") else []

    def get_val(key, section_names, default=""):
        for sec in section_names:
            if sec in doc and isinstance(doc[sec], dict) and key in doc[sec]:
                return doc[sec][key]
        return doc.get(key, default)

    culture_and_heritage = {
        "culture_image_url": get_val("culture_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_dances": get_val("traditional_dances", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_dances_image_url": get_val("traditional_dances_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_music": get_val("traditional_music", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_music_image_url": get_val("traditional_music_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "festivals": get_val("festivals", ["Culture & Heritage", "culture_and_heritage"], ""),
        "festivals_image_url": get_val("festivals_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_clothing": get_val("traditional_clothing", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_clothing_image_url": get_val("traditional_clothing_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "culture_arts_crafts": get_val("culture_arts_crafts", ["Culture & Heritage", "culture_and_heritage"], ""),
        "culture_arts_crafts_image_url": get_val("culture_arts_crafts_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "culture_food": get_val("culture_food", ["Culture & Heritage", "culture_and_heritage"], ""),
        "culture_food_image_url": get_val("culture_food_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditions_customs": get_val("traditions_customs", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditions_customs_image_url": get_val("traditions_customs_image_url", ["Culture & Heritage", "culture_and_heritage"], "")
    }

    heritage_and_monuments = {
        "heritage_image_url": get_val("heritage_image_url", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "historical_monuments": get_val("historical_monuments", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "historical_monuments_image_url": get_val("historical_monuments_image_url", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "temples_churches_mosques": get_val("temples_churches_mosques", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "temples_churches_mosques_image_url": get_val("temples_churches_mosques_image_url", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "forts": get_val("forts", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "forts_image_url": get_val("forts_image_url", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "unesco_heritage": get_val("unesco_heritage", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "unesco_heritage_image_url": get_val("unesco_heritage_image_url", ["Heritage & Monuments", "heritage_and_monuments"], "")
    }

    geography = {
        "geography_image_url": get_val("geography_image_url", ["Geography", "geography"], ""),
        "major_rivers": get_val("major_rivers", ["Geography", "geography"], ""),
        "major_rivers_image_url": get_val("major_rivers_image_url", ["Geography", "geography"], ""),
        "mountains": get_val("mountains", ["Geography", "geography"], ""),
        "mountains_image_url": get_val("mountains_image_url", ["Geography", "geography"], ""),
        "beaches": get_val("beaches", ["Geography", "geography"], ""),
        "beaches_image_url": get_val("beaches_image_url", ["Geography", "geography"], ""),
        "forests": get_val("forests", ["Geography", "geography"], ""),
        "forests_image_url": get_val("forests_image_url", ["Geography", "geography"], ""),
        "climate": get_val("climate", ["Geography", "geography"], ""),
        "climate_image_url": get_val("climate_image_url", ["Geography", "geography"], "")
    }

    food_and_lifestyle = {
        "food_image_url": get_val("food_image_url", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "famous_dishes": get_val("famous_dishes", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "famous_dishes_image_url": get_val("famous_dishes_image_url", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "traditional_cuisine": get_val("traditional_cuisine", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "traditional_cuisine_image_url": get_val("traditional_cuisine_image_url", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "famous_ingredients": get_val("famous_ingredients", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "famous_ingredients_image_url": get_val("famous_ingredients_image_url", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], "")
    }

    traditional_lifestyle = {
        "lifestyle_image_url": get_val("lifestyle_image_url", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "traditional_dress": get_val("traditional_dress", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "traditional_dress_image_url": get_val("traditional_dress_image_url", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "occupations": get_val("occupations", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "occupations_image_url": get_val("occupations_image_url", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "local_communities": get_val("local_communities", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "local_communities_image_url": get_val("local_communities_image_url", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], "")
    }

    highlights_and_places = {
        "highlights_image_url": get_val("highlights_image_url", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_arts_crafts": get_val("famous_arts_crafts", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_arts_crafts_image_url": get_val("famous_arts_crafts_image_url", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_personalities": get_val("famous_personalities", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_personalities_image_url": get_val("famous_personalities_image_url", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_places": get_val("famous_places", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_places_image_url": get_val("famous_places_image_url", ["Highlights & Places", "highlights_and_places"], "")
    }

    subfield_keys_to_remove = [
        "culture_image_url", "traditional_dances", "traditional_dances_image_url", "traditional_music",
        "traditional_music_image_url", "festivals", "festivals_image_url", "traditional_clothing",
        "traditional_clothing_image_url", "culture_arts_crafts", "culture_arts_crafts_image_url",
        "culture_food", "culture_food_image_url", "traditions_customs", "traditions_customs_image_url",
        "heritage_image_url", "historical_monuments", "historical_monuments_image_url",
        "temples_churches_mosques", "temples_churches_mosques_image_url", "forts", "forts_image_url",
        "unesco_heritage", "unesco_heritage_image_url",
        "geography_image_url", "major_rivers", "major_rivers_image_url", "mountains", "mountains_image_url",
        "beaches", "beaches_image_url", "forests", "forests_image_url", "climate", "climate_image_url",
        "food_image_url", "famous_dishes", "famous_dishes_image_url", "traditional_cuisine",
        "traditional_cuisine_image_url", "famous_ingredients", "famous_ingredients_image_url",
        "lifestyle_image_url", "traditional_dress", "traditional_dress_image_url", "occupations",
        "occupations_image_url", "local_communities", "local_communities_image_url",
        "highlights_image_url", "famous_arts_crafts", "famous_arts_crafts_image_url", "famous_personalities",
        "famous_personalities_image_url", "famous_places", "famous_places_image_url",
        "traditional_dances_title", "festivals_title",
        "culture_and_heritage", "heritage_and_monuments", "food_and_traditional_lifestyle",
        "traditional_lifestyle_and_culture", "highlights_and_places"
    ]
    for k in subfield_keys_to_remove:
        doc.pop(k, None)

    doc["Culture & Heritage"] = culture_and_heritage
    doc["Heritage & Monuments"] = heritage_and_monuments
    doc["Geography"] = geography
    doc["Food & Traditional Lifestyle"] = food_and_lifestyle
    doc["Traditional Lifestyle & Culture"] = traditional_lifestyle
    doc["Highlights & Places"] = highlights_and_places

    return doc

def save_and_optimize_image(file_obj, filepath: str, max_dim: int = 1920):
    """Saves uploaded image, automatically resizing & compressing to optimize load times."""
    try:
        file_bytes = file_obj.file.read()
        file_obj.file.seek(0)
        img = Image.open(io.BytesIO(file_bytes))

        w, h = img.size
        if w > max_dim or h > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        ext = os.path.splitext(filepath)[1].lower()
        if ext in [".jpg", ".jpeg"]:
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(filepath, format="JPEG", quality=85, optimize=True)
        elif ext == ".webp":
            img.save(filepath, format="WEBP", quality=85, optimize=True)
        elif ext == ".png":
            if img.mode == "RGBA":
                img.save(filepath, format="PNG", optimize=True)
            else:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(filepath, format="JPEG", quality=85, optimize=True)
        else:
            with open(filepath, "wb") as buffer:
                shutil.copyfileobj(file_obj.file, buffer)
    except Exception:
        file_obj.file.seek(0)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file_obj.file, buffer)

@router.get("", response_model=List[IndianExplorerResponse])
async def get_all_indian_entities(current_admin: dict = Depends(require_permission("Indian Explorer", "read"))):
    """Retrieve all Indian Explorer entities ordered by order number (Requires Admin Authentication)"""
    cursor = db.indian_explorer.find().sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]

@router.post("", response_model=IndianExplorerResponse)
async def create_indian_entity(data: IndianExplorerCreate, current_admin: dict = Depends(require_permission("Indian Explorer", "create"))):
    """Create a new Indian Explorer entity (Requires Admin Authentication)"""
    existing = await db.indian_explorer.find_one({"name": {"$regex": f"^{data.name.strip()}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail=f"Indian entity '{data.name}' already exists.")

    new_doc = data.model_dump()
    new_doc["created_at"] = datetime.now(timezone.utc)
    new_doc["updated_at"] = datetime.now(timezone.utc)

    result = await db.indian_explorer.insert_one(new_doc)
    created = await db.indian_explorer.find_one({"_id": result.inserted_id})
    return serialize_doc(created)

# --- STATIC SPECIFIC ROUTES (MUST be defined before dynamic /{item_id} routes) ---

@router.get("/uploaded-images")
async def get_uploaded_indian_images(current_admin: dict = Depends(require_permission("Indian Explorer", "read"))):
    """List all uploaded images stored in indian uploads directory with size metadata."""
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
                "url": f"/uploads/indian/{filename}",
                "size_bytes": size_bytes,
                "size_formatted": size_formatted,
                "mtime": stat.st_mtime
            })

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items

@router.delete("/uploaded-images/{filename}")
async def delete_uploaded_indian_image(filename: str, current_admin: dict = Depends(require_permission("Indian Explorer", "delete"))):
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
async def upload_indian_image(file: UploadFile = File(...), current_admin: dict = Depends(require_permission("Indian Explorer", "create"))):
    """Upload a single image file for indian feature image or cover image (Requires Admin Authentication)"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image format (JPEG, PNG, WEBP, SVG)")

    ext = os.path.splitext(file.filename)[1] or ".png"
    filename = f"indian_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    save_and_optimize_image(file, filepath)

    relative_url = f"/uploads/indian/{filename}"
    return {"message": "Image uploaded successfully", "url": relative_url}

@router.post("/upload-multiple-images")
async def upload_multiple_indian_images(files: List[UploadFile] = File(...), current_admin: dict = Depends(require_permission("Indian Explorer", "create"))):
    """Upload multiple image files for indian gallery (Requires Admin Authentication)"""
    uploaded_urls = []
    for file in files:
        if file.content_type.startswith("image/"):
            ext = os.path.splitext(file.filename)[1] or ".png"
            filename = f"indian_gal_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
            filepath = os.path.join(UPLOAD_DIR, filename)

            save_and_optimize_image(file, filepath)

            uploaded_urls.append(f"/uploads/indian/{filename}")

    return {"message": f"{len(uploaded_urls)} images uploaded successfully", "urls": uploaded_urls}

# --- DYNAMIC PARAMETER ROUTES (defined after specific static routes) ---

@router.get("/{item_id}", response_model=IndianExplorerResponse)
async def get_indian_entity(item_id: str, current_admin: dict = Depends(require_permission("Indian Explorer", "read"))):
    """Get single Indian Explorer entity by ID (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    doc = await db.indian_explorer.find_one({"_id": ObjectId(item_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Indian entity not found")

    return serialize_doc(doc)

@router.put("/{item_id}", response_model=IndianExplorerResponse)
async def update_indian_entity(item_id: str, update_data: IndianExplorerUpdate, current_admin: dict = Depends(require_permission("Indian Explorer", "update"))):
    """Update an existing Indian Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    fields = {k: v for k, v in update_data.model_dump(exclude_unset=True).items()}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    fields["updated_at"] = datetime.now(timezone.utc)

    result = await db.indian_explorer.update_one(
        {"_id": ObjectId(item_id)},
        {"$set": fields}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Indian entity not found")

    updated = await db.indian_explorer.find_one({"_id": ObjectId(item_id)})
    return serialize_doc(updated)

@router.delete("/{item_id}")
async def delete_indian_entity(item_id: str, current_admin: dict = Depends(require_permission("Indian Explorer", "delete"))):
    """Delete an Indian Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.indian_explorer.delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Indian entity not found")

    return {"message": "Indian entity deleted successfully", "id": item_id}
