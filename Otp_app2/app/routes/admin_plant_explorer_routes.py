import os
import shutil
import io
import json
import urllib.parse
import urllib.request
from typing import List, Optional
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from PIL import Image
from pydantic import BaseModel

from app.core.database import db
from app.models.explorer_models import PlantExplorerCreate, PlantExplorerUpdate, PlantExplorerResponse
from app.utils.admin_auth import require_permission

router = APIRouter(prefix="/plant-explorer", tags=["Plant Explorer - Admin"])

class PlantExplorerGenerateRequest(BaseModel):
    name: str
    category: Optional[str] = "Trees"

UPLOAD_DIR = os.path.join("app", "static", "uploads", "plant")
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
    for k in ["flower_image_url", "flower_description", "leaf_image_url", "leaf_description", "stem_image_url", "stem_description", "fruit_image_url", "fruit_description"]:
        if k not in doc or doc[k] is None:
            doc[k] = ""
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

def fetch_wiki_image_url(query: str) -> Optional[str]:
    """Fetches real high-resolution image URL from Wikipedia / Wikimedia Commons matching query."""
    if not query or not query.strip():
        return None
    
    clean_q = query.strip()
    try:
        url = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(clean_q)}&prop=pageimages&pithumbsize=1000&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "MikiPlantExplorer/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            pages = data.get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                if "thumbnail" in pdata and pdata["thumbnail"].get("source"):
                    return pdata["thumbnail"]["source"]
    except Exception as e:
        print(f"[WARN] Wikipedia thumbnail fetch warning for '{clean_q}': {e}")

    try:
        url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(clean_q)}&gsrnamespace=6&prop=imageinfo&iiprop=url&iiurlwidth=800&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "MikiPlantExplorer/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            pages = data.get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                imageinfo = pdata.get("imageinfo", [])
                if imageinfo and isinstance(imageinfo, list) and len(imageinfo) > 0:
                    img = imageinfo[0].get("thumburl") or imageinfo[0].get("url")
                    if img and any(img.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                        return img
    except Exception as e:
        print(f"[WARN] Wikimedia search fetch warning for '{clean_q}': {e}")

    return None

def resolve_species_correct_images(name: str, category: str = "Trees") -> dict:
    """Dynamically fetches real plant species images for main, banner, flower, leaf, stem, and fruit."""
    name_clean = name.strip()

    main_img = fetch_wiki_image_url(name_clean) or fetch_wiki_image_url(f"{name_clean} plant")
    flower_img = fetch_wiki_image_url(f"{name_clean} flower") or fetch_wiki_image_url(f"{name_clean} blossom") or main_img
    leaf_img = fetch_wiki_image_url(f"{name_clean} leaf") or fetch_wiki_image_url(f"{name_clean} foliage") or main_img
    stem_img = fetch_wiki_image_url(f"{name_clean} stem") or fetch_wiki_image_url(f"{name_clean} bark") or main_img
    fruit_img = fetch_wiki_image_url(f"{name_clean} fruit") or fetch_wiki_image_url(f"{name_clean} seed") or main_img
    banner_img = fetch_wiki_image_url(f"{name_clean} tree") or main_img

    # Category fallback graphics if network search returns None
    cat_fallbacks = {
        "Trees": {
            "image": "https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=1200&q=80",
            "flower": "https://images.unsplash.com/photo-1526047932273-341f2a7631f9?auto=format&fit=crop&w=800&q=80",
            "leaf": "https://images.unsplash.com/photo-1501004318641-b39e6451bec6?auto=format&fit=crop&w=800&q=80",
            "stem": "https://images.unsplash.com/photo-1542273917363-3b1817f69a2d?auto=format&fit=crop&w=800&q=80",
            "fruit": "https://images.unsplash.com/photo-1509316975850-ff9c5deb0cd9?auto=format&fit=crop&w=800&q=80"
        },
        "Flowering Plants": {
            "image": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1490750967868-88aa4486c946?auto=format&fit=crop&w=1200&q=80",
            "flower": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=800&q=80",
            "leaf": "https://images.unsplash.com/photo-1533038590840-1cde6e668a91?auto=format&fit=crop&w=800&q=80",
            "stem": "https://images.unsplash.com/photo-1502082553048-f009c37129b9?auto=format&fit=crop&w=800&q=80",
            "fruit": "https://images.unsplash.com/photo-1618897996318-5a901fa6ca71?auto=format&fit=crop&w=800&q=80"
        }
    }
    fb = cat_fallbacks.get(category, cat_fallbacks["Trees"])

    final_main = main_img or fb["image"]
    final_banner = banner_img or fb["banner"]
    final_flower = flower_img or fb["flower"]
    final_leaf = leaf_img or fb["leaf"]
    final_stem = stem_img or fb["stem"]
    final_fruit = fruit_img or fb["fruit"]

    return {
        "image_url": final_main,
        "banner_image_url": final_banner,
        "flower_image_url": final_flower,
        "leaf_image_url": final_leaf,
        "stem_image_url": final_stem,
        "fruit_image_url": final_fruit,
        "gallery_images": [final_main, final_flower, final_leaf]
    }

@router.get("", response_model=List[PlantExplorerResponse])
async def get_all_plant_entities(current_admin: dict = Depends(require_permission("Plant Explorer", "read"))):
    """Retrieve all Plant Explorer entities ordered by order number (Requires Admin Authentication)"""
    cursor = db.plant_explorer.find().sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]

@router.post("", response_model=PlantExplorerResponse)
async def create_plant_entity(data: PlantExplorerCreate, current_admin: dict = Depends(require_permission("Plant Explorer", "create"))):
    """Create a new Plant Explorer entity (Requires Admin Authentication)"""
    existing = await db.plant_explorer.find_one({"name": {"$regex": f"^{data.name.strip()}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail=f"Plant entity '{data.name}' already exists.")

    new_doc = data.model_dump()
    new_doc["created_at"] = datetime.now(timezone.utc)
    new_doc["updated_at"] = datetime.now(timezone.utc)

    result = await db.plant_explorer.insert_one(new_doc)
    created = await db.plant_explorer.find_one({"_id": result.inserted_id})
    return serialize_doc(created)

# --- STATIC SPECIFIC ROUTES (MUST be defined before dynamic /{item_id} routes) ---

@router.get("/uploaded-images")
async def get_uploaded_plant_images(current_admin: dict = Depends(require_permission("Plant Explorer", "read"))):
    """List all uploaded images stored in plant uploads directory with size metadata."""
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
                "url": f"/uploads/plant/{filename}",
                "size_bytes": size_bytes,
                "size_formatted": size_formatted,
                "mtime": stat.st_mtime
            })

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items

@router.delete("/uploaded-images/{filename}")
async def delete_uploaded_plant_image(filename: str, current_admin: dict = Depends(require_permission("Plant Explorer", "delete"))):
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
async def upload_plant_image(file: UploadFile = File(...), current_admin: dict = Depends(require_permission("Plant Explorer", "create"))):
    """Upload a single image file for plant image or cover image (Requires Admin Authentication)"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image format (JPEG, PNG, WEBP, SVG)")

    ext = os.path.splitext(file.filename)[1] or ".png"
    filename = f"plant_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    save_and_optimize_image(file, filepath)

    relative_url = f"/uploads/plant/{filename}"
    return {"message": "Image uploaded successfully", "url": relative_url}

@router.post("/upload-multiple-images")
async def upload_multiple_plant_images(files: List[UploadFile] = File(...), current_admin: dict = Depends(require_permission("Plant Explorer", "create"))):
    """Upload multiple image files for plant gallery (Requires Admin Authentication)"""
    uploaded_urls = []
    for file in files:
        if file.content_type.startswith("image/"):
            ext = os.path.splitext(file.filename)[1] or ".png"
            filename = f"plant_gal_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
            filepath = os.path.join(UPLOAD_DIR, filename)

            save_and_optimize_image(file, filepath)

            uploaded_urls.append(f"/uploads/plant/{filename}")

    return {"message": f"{len(uploaded_urls)} images uploaded successfully", "urls": uploaded_urls}

async def generate_plant_data_ai(name: str, category: str = "Trees"):
    name_clean = name.strip() if name else "Plant Species"
    species_imgs = resolve_species_correct_images(name_clean, category)

    prompt = f"""Generate a detailed botanical JSON object for Plant Explorer for the plant species: '{name_clean}'.
Category: {category}.
Return JSON with fields:
name, scientific_name, family, habitat, climate, fun_fact, short_description, full_description, descriptions (array of 2 detailed strings),
flower_description, leaf_description, stem_description, fruit_description.
Return ONLY raw valid JSON."""

    try:
        from app.core.openai_client import get_async_openai_client, get_openai_api_key
        api_key = get_openai_api_key()
        if api_key and api_key != "sk-placeholder":
            client = get_async_openai_client()
            resp = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a master botanist and plant taxonomy expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            content = resp.choices[0].message.content
            ai_json = json.loads(content)
            ai_json["name"] = name_clean.title()
            ai_json["category"] = category
            for fk, iu in species_imgs.items():
                ai_json.setdefault(fk, iu)
            return serialize_doc(ai_json)
    except Exception as e:
        print(f"[WARN] OpenAI generation fallback for plant explorer: {e}")

    ai_json = {
        "name": name_clean.title(),
        "category": category,
        "scientific_name": f"{name_clean.title()} scientifica",
        "family": f"{name_clean.title()}aceae",
        "habitat": f"Native habitat & temperate climate regions of {name_clean.title()}",
        "climate": "Moderate to Warm Subtropical / Tropical Climate",
        "fun_fact": f"{name_clean.title()} is well known for its unique botanical adaptations and ecological significance!",
        "short_description": f"{name_clean.title()} is a fascinating plant species belonging to the {category} category.",
        "full_description": f"{name_clean.title()} features distinct anatomical characteristics, vibrant foliage, and vital environmental benefits for local biodiversity.",
        "descriptions": [
            f"{name_clean.title()} exhibits specialized growth patterns and unique foliage structure suited to its native climate.",
            f"Botanically categorized under {category}, {name_clean.title()} plays an important role in soil conservation and supporting local pollinators."
        ],
        "flower_description": f"The blossom of {name_clean.title()} displays delicate petals and distinct floral structures designed for attracting natural pollinators.",
        "leaf_description": f"The foliage features rich green leaves with intricate vascular venation, optimized for efficient photosynthesis.",
        "stem_description": f"The stem and bark structure provides strong skeletal support, vascular transport, and protective outer tissue.",
        "fruit_description": f"The fruit and seed pods contain protective outer husks housing seeds for species propagation."
    }
    for fk, iu in species_imgs.items():
        ai_json.setdefault(fk, iu)

    return serialize_doc(ai_json)

@router.post("/generate-content")
async def generate_plant_content_route(
    req: PlantExplorerGenerateRequest,
    current_admin: dict = Depends(require_permission("Plant Explorer", "create"))
):
    """Auto-generate comprehensive botanical content & plant parts image URLs for a plant species using AI."""
    name_clean = req.name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Plant species name is required")

    data = await generate_plant_data_ai(name_clean, req.category)
    return data

# --- DYNAMIC PARAMETER ROUTES (defined after specific static routes) ---

@router.get("/{item_id}", response_model=PlantExplorerResponse)
async def get_plant_entity(item_id: str, current_admin: dict = Depends(require_permission("Plant Explorer", "read"))):
    """Get single Plant Explorer entity by ID (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    doc = await db.plant_explorer.find_one({"_id": ObjectId(item_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Plant entity not found")

    return serialize_doc(doc)

@router.put("/{item_id}", response_model=PlantExplorerResponse)
async def update_plant_entity(item_id: str, update_data: PlantExplorerUpdate, current_admin: dict = Depends(require_permission("Plant Explorer", "update"))):
    """Update an existing Plant Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    fields = {k: v for k, v in update_data.model_dump(exclude_unset=True).items()}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    fields["updated_at"] = datetime.now(timezone.utc)

    result = await db.plant_explorer.update_one(
        {"_id": ObjectId(item_id)},
        {"$set": fields}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Plant entity not found")

    updated = await db.plant_explorer.find_one({"_id": ObjectId(item_id)})
    return serialize_doc(updated)

@router.delete("/{item_id}")
async def delete_plant_entity(item_id: str, current_admin: dict = Depends(require_permission("Plant Explorer", "delete"))):
    """Delete a Plant Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.plant_explorer.delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Plant entity not found")

    return {"message": "Plant entity deleted successfully", "id": item_id}
