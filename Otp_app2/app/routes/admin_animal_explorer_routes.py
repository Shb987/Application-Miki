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
from app.models.explorer_models import AnimalExplorerCreate, AnimalExplorerUpdate, AnimalExplorerResponse
from app.utils.admin_auth import require_permission

router = APIRouter(prefix="/animal-explorer", tags=["Animal Explorer - Admin"])

class AnimalExplorerGenerateRequest(BaseModel):
    name: str
    category: Optional[str] = "Wild Animals"

UPLOAD_DIR = os.path.join("app", "static", "uploads", "animal")
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
    if "interesting_facts" not in doc or doc["interesting_facts"] is None:
        doc["interesting_facts"] = []

    # Ensure all string fields default gracefully
    str_fields = [
        "scientific_name", "family", "habitat",
        "climate_zone", "conservation_status", "fun_fact", "short_summary",
        "short_description", "full_description", "image_url", "banner_image_url",
        "appearance_image_url", "appearance_description",
        "habitat_image_url", "habitat_description",
        "diet_image_url", "diet_description",
        "sound_audio_url", "sound_image_url", "sound_description",
        "body_parts_image_url", "body_parts_description",
        "life_cycle_image_url", "life_cycle_description",
        "adaptations_image_url", "adaptations_description",
        "offspring_image_url", "offspring_description",
        "diet_type", "lifespan", "size_weight", "movement_type", "language"
    ]
    for k in str_fields:
        if k not in doc or doc[k] is None:
            doc[k] = ""
    return doc

def save_and_optimize_image(file_obj, filepath: str, max_dim: int = 1920):
    """Saves uploaded image, resizing & compressing to optimize load times while preserving PNG transparency."""
    try:
        file_bytes = file_obj.file.read()
        file_obj.file.seek(0)
        img = Image.open(io.BytesIO(file_bytes))

        w, h = img.size
        if w > max_dim or h > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        ext = os.path.splitext(filepath)[1].lower()
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

_wiki_cache = {}

def fetch_wiki_image_url(query: str) -> Optional[str]:
    """Fetches real high-resolution image URL from Wikipedia, cached and rate-limit safe."""
    if not query or not query.strip():
        return None
    
    clean_q = query.strip().lower()
    if clean_q in _wiki_cache:
        return _wiki_cache[clean_q]

    try:
        url = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(query.strip())}&prop=pageimages&pithumbsize=1000&format=json"
        req = urllib.request.Request(url, headers={
            "User-Agent": "MikiApp/1.0 (educational-platform; contact@miki-app.internal)"
        })
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            pages = data.get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                if "thumbnail" in pdata and pdata["thumbnail"].get("source"):
                    img_url = pdata["thumbnail"]["source"]
                    _wiki_cache[clean_q] = img_url
                    return img_url
    except Exception:
        # Silent return None on any network or rate-limit issue - zero log spam
        pass

    _wiki_cache[clean_q] = None
    return None

def resolve_animal_correct_images(name: str, category: str = "Wild Animals") -> dict:
    """Dynamically resolves real animal species images using single safe lookup and curated category visuals."""
    name_clean = name.strip()

    # Exactly ONE safe query to Wikipedia for the species
    species_img = fetch_wiki_image_url(name_clean)

    # High quality Unsplash fallbacks tailored per category
    category_fallbacks = {
        "Wild Animals": {
            "image": "https://images.unsplash.com/photo-1546182990-dffeafbe841d?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1534188753412-3e26d0d618d6?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1546182990-dffeafbe841d?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1517849845537-4d257902454a?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1534188753412-3e26d0d618d6?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1564349683136-77e08dba1ef7?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1546182990-dffeafbe841d?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1564349683136-77e08dba1ef7?auto=format&fit=crop&w=800&q=80"
        },
        "Domestic Animals & Pets": {
            "image": "https://images.unsplash.com/photo-1543466835-00a7907e9de1?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1601758228041-f3b2795255f1?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1543466835-00a7907e9de1?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1543466835-00a7907e9de1?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1591160690555-5debfba289f0?auto=format&fit=crop&w=800&q=80"
        },
        "Insects": {
            "image": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1516205651411-aef33a44f7c2?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1516205651411-aef33a44f7c2?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1516205651411-aef33a44f7c2?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1516205651411-aef33a44f7c2?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1516205651411-aef33a44f7c2?auto=format&fit=crop&w=800&q=80"
        },
        "Reptiles": {
            "image": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=800&q=80"
        },
        "Mammals": {
            "image": "https://images.unsplash.com/photo-1557050543-4d5f4e07ef46?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1534567153574-2b12153a87f0?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1557050543-4d5f4e07ef46?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1534567153574-2b12153a87f0?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1557050543-4d5f4e07ef46?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1534567153574-2b12153a87f0?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1557050543-4d5f4e07ef46?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1557050543-4d5f4e07ef46?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1534567153574-2b12153a87f0?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1557050543-4d5f4e07ef46?auto=format&fit=crop&w=800&q=80"
        },
        "Birds": {
            "image": "https://images.unsplash.com/photo-1444464666168-49d633b86797?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1452570053594-1b985d6ea890?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1444464666168-49d633b86797?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1452570053594-1b985d6ea890?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1444464666168-49d633b86797?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1452570053594-1b985d6ea890?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1444464666168-49d633b86797?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1452570053594-1b985d6ea890?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1444464666168-49d633b86797?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1444464666168-49d633b86797?auto=format&fit=crop&w=800&q=80"
        },
        "Amphibians": {
            "image": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1508873696983-2df57036476b?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1508873696983-2df57036476b?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1508873696983-2df57036476b?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1508873696983-2df57036476b?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?auto=format&fit=crop&w=800&q=80"
        },
        "Aquatic & Marine Animals": {
            "image": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80"
        },
        "Endangered Animals": {
            "image": "https://images.unsplash.com/photo-1564349683136-77e08dba1ef7?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1500485035595-cbe6f645feb1?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1564349683136-77e08dba1ef7?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1500485035595-cbe6f645feb1?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1564349683136-77e08dba1ef7?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1500485035595-cbe6f645feb1?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1564349683136-77e08dba1ef7?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1564349683136-77e08dba1ef7?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1500485035595-cbe6f645feb1?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1564349683136-77e08dba1ef7?auto=format&fit=crop&w=800&q=80"
        },
        "Prehistoric Animals": {
            "image": "https://images.unsplash.com/photo-1570481662006-a3a1374699e8?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1525874684015-58379d421a52?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1570481662006-a3a1374699e8?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1525874684015-58379d421a52?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1570481662006-a3a1374699e8?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1525874684015-58379d421a52?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1570481662006-a3a1374699e8?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1525874684015-58379d421a52?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1570481662006-a3a1374699e8?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1570481662006-a3a1374699e8?auto=format&fit=crop&w=800&q=80"
        },
        "Arachnids": {
            "image": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80"
        },
        "Worms & Other Invertebrates": {
            "image": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "banner": "https://images.unsplash.com/photo-1508873696983-2df57036476b?auto=format&fit=crop&w=1200&q=80",
            "appearance": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "habitat": "https://images.unsplash.com/photo-1508873696983-2df57036476b?auto=format&fit=crop&w=800&q=80",
            "diet": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "sound": "https://images.unsplash.com/photo-1508873696983-2df57036476b?auto=format&fit=crop&w=800&q=80",
            "body_parts": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "lifecycle": "https://images.unsplash.com/photo-1508873696983-2df57036476b?auto=format&fit=crop&w=800&q=80",
            "adaptations": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80",
            "offspring": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80"
        }
    }
    fb = category_fallbacks.get(category, category_fallbacks["Wild Animals"])

    final_main = species_img or fb["image"]
    final_banner = species_img or fb["banner"]
    final_appearance = species_img or fb.get("appearance", final_main)
    final_habitat = fb.get("habitat", final_main)
    final_diet = fb.get("diet", final_main)
    final_sound = fb.get("sound", final_main)
    final_body_parts = fb.get("body_parts", final_main)
    final_lifecycle = fb.get("lifecycle", final_main)
    final_adaptations = fb.get("adaptations", final_main)
    final_offspring = fb.get("offspring", final_main)

    gallery = [final_main, final_appearance, final_habitat, final_offspring]

    return {
        "image_url": final_main,
        "banner_image_url": final_banner,
        "appearance_image_url": final_appearance,
        "habitat_image_url": final_habitat,
        "diet_image_url": final_diet,
        "sound_audio_url": final_sound,
        "sound_image_url": final_sound,
        "body_parts_image_url": final_body_parts,
        "life_cycle_image_url": final_lifecycle,
        "adaptations_image_url": final_adaptations,
        "offspring_image_url": final_offspring,
        "gallery_images": gallery
    }

@router.get("", response_model=List[AnimalExplorerResponse])
async def get_all_animal_entities(current_admin: dict = Depends(require_permission("Animal Explorer", "read"))):
    """Retrieve all Animal Explorer entities ordered by display order (Requires Admin Authentication)"""
    cursor = db.animal_explorer.find().sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]

@router.post("", response_model=AnimalExplorerResponse)
async def create_animal_entity(data: AnimalExplorerCreate, current_admin: dict = Depends(require_permission("Animal Explorer", "create"))):
    """Create a new Animal Explorer entity (Requires Admin Authentication)"""
    existing = await db.animal_explorer.find_one({"name": {"$regex": f"^{data.name.strip()}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail=f"Animal entity '{data.name}' already exists.")

    new_doc = data.model_dump()
    new_doc["created_at"] = datetime.now(timezone.utc)
    new_doc["updated_at"] = datetime.now(timezone.utc)

    result = await db.animal_explorer.insert_one(new_doc)
    created = await db.animal_explorer.find_one({"_id": result.inserted_id})
    return serialize_doc(created)

# --- STATIC SPECIFIC ROUTES (MUST be defined before dynamic /{item_id} routes) ---

@router.get("/uploaded-images")
async def get_uploaded_animal_images(current_admin: dict = Depends(require_permission("Animal Explorer", "read"))):
    """List all uploaded images stored in animal uploads directory with size metadata."""
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
                "url": f"/uploads/animal/{filename}",
                "size_bytes": size_bytes,
                "size_formatted": size_formatted,
                "mtime": stat.st_mtime
            })

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items

@router.delete("/uploaded-images/{filename}")
async def delete_uploaded_animal_image(filename: str, current_admin: dict = Depends(require_permission("Animal Explorer", "delete"))):
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
async def upload_animal_image(file: UploadFile = File(...), current_admin: dict = Depends(require_permission("Animal Explorer", "create"))):
    """Upload a single image file for animal characteristics or covers (Requires Admin Authentication)"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image format (JPEG, PNG, WEBP, SVG)")

    ext = os.path.splitext(file.filename)[1] or ".png"
    filename = f"animal_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    save_and_optimize_image(file, filepath)

    relative_url = f"/uploads/animal/{filename}"
    return {"message": "Image uploaded successfully", "url": relative_url}

@router.post("/upload-multiple-images")
async def upload_multiple_animal_images(files: List[UploadFile] = File(...), current_admin: dict = Depends(require_permission("Animal Explorer", "create"))):
    """Upload multiple image files for species gallery carousel (Requires Admin Authentication)"""
    uploaded_urls = []
    for file in files:
        if file.content_type.startswith("image/"):
            ext = os.path.splitext(file.filename)[1] or ".png"
            filename = f"animal_gal_{int(datetime.now().timestamp())}_{os.urandom(4).hex()}{ext}"
            filepath = os.path.join(UPLOAD_DIR, filename)

            save_and_optimize_image(file, filepath)
            uploaded_urls.append(f"/uploads/animal/{filename}")

    return {"message": f"{len(uploaded_urls)} images uploaded successfully", "urls": uploaded_urls}

async def generate_animal_data_ai(name: str, category: str = "Wild Animals"):
    name_clean = name.strip() if name else "Animal Species"
    species_imgs = resolve_animal_correct_images(name_clean, category)

    prompt = f"""Generate a comprehensive zoological and wildlife JSON object for Animal Explorer for the species: '{name_clean}'.
Category: '{category}'.

Return a valid JSON object strictly containing:
- name: Capitalized Common Name (e.g. 'African Lion')
- scientific_name: Binomial scientific nomenclature (e.g. 'Panthera leo')
- family: Biological family (e.g. 'Felidae')
- habitat: Primary habitat/region (e.g. 'Grasslands, savannas, and open woodlands of Sub-Saharan Africa')
- climate_zone: Climate (e.g. 'Tropical and Subtropical Savanna')
- fun_fact: Captivating kid-friendly fun fact with exclamation
- short_summary: 1-2 sentence engaging overview
- full_description: 3-4 sentence comprehensive description
- descriptions: Array of exactly 3 distinct detailed paragraph strings (Desc 1, Desc 2, Desc 3)
- appearance_description: Physical appearance, fur/scales/feathers, coloration, body structure
- habitat_description: Natural territory, shelter, weather preferences
- diet_description: Food habits, prey or vegetation eaten, hunting or foraging tactics
- sound_description: Vocalizations, roaring, calls, frequencies, purpose of sounds
- body_parts_description: Claws, teeth, limbs, tail, sense organs, anatomy
- life_cycle_description: Mating, gestation/incubation, lifespan, stages from juvenile to adult
- adaptations_description: Camouflage, speed, night vision, thermal regulation, survival skills
- offspring_description: Litter/clutch size, maternal care, names of young (cubs/pups/chicks/etc.)
- diet_type: One of 'Herbivore', 'Carnivore', 'Omnivore', 'Insectivore', 'Other'
- lifespan: Typical lifespan (e.g. '10 - 15 years in the wild, up to 20 years in captivity')
- size_weight: Measurements (e.g. 'Body length: 1.8 - 2.1 m | Weight: 150 - 250 kg')
- movement_type: One of 'Walking', 'Running', 'Flying', 'Swimming', 'Crawling', 'Hopping'
- interesting_facts: Array of 3-4 fascinating bullet-point facts

Return ONLY the raw JSON object."""

    try:
        from app.core.openai_client import get_async_openai_client, get_openai_api_key
        api_key = get_openai_api_key()
        if api_key and api_key != "sk-placeholder":
            import asyncio
            client = get_async_openai_client()
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a master zoologist, wildlife biologist, and animal taxonomy expert."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    response_format={"type": "json_object"}
                ),
                timeout=10.0
            )
            content = resp.choices[0].message.content
            ai_json = json.loads(content)
            ai_json["name"] = name_clean.title()
            ai_json["category"] = category
            ai_json["short_description"] = ai_json.get("short_summary", "")
            ai_json["conservation_status"] = ""

            # Merge species image URLs
            for fk, iu in species_imgs.items():
                ai_json.setdefault(fk, iu)
            return serialize_doc(ai_json)
    except Exception as e:
        print(f"[INFO] Using instant zoological fallback for animal explorer: {e}")

    # Fallback zoological generator
    diet_map = {
        "Wild Animals": "Carnivore",
        "Domestic Animals & Pets": "Omnivore",
        "Insects": "Insectivore",
        "Reptiles": "Carnivore",
        "Mammals": "Herbivore",
        "Birds": "Omnivore",
        "Amphibians": "Insectivore",
        "Aquatic & Marine Animals": "Carnivore",
        "Endangered Animals": "Herbivore",
        "Prehistoric Animals": "Carnivore",
        "Arachnids": "Carnivore",
        "Worms & Other Invertebrates": "Herbivore"
    }
    mov_map = {
        "Birds": "Flying",
        "Aquatic & Marine Animals": "Swimming",
        "Insects": "Flying",
        "Reptiles": "Crawling",
        "Amphibians": "Hopping",
        "Arachnids": "Crawling",
        "Worms & Other Invertebrates": "Crawling"
    }

    diet_type_default = diet_map.get(category, "Omnivore")
    movement_type_default = mov_map.get(category, "Walking")

    ai_json = {
        "name": name_clean.title(),
        "category": category,
        "scientific_name": f"{name_clean.title()} scientificus",
        "family": f"{name_clean.title()}idae",
        "habitat": f"Native wild forests, grasslands, and protected reserves inhabited by {name_clean.title()}",
        "climate_zone": "Tropical, Subtropical, and Temperate Climate Zones",
        "conservation_status": "",
        "fun_fact": f"Did you know? The {name_clean.title()} has exceptional senses and plays a key role in maintaining biodiversity!",
        "short_summary": f"The {name_clean.title()} is a remarkable species classified under {category}, celebrated for its unique survival behaviors and ecological importance.",
        "short_description": f"The {name_clean.title()} is a remarkable species classified under {category}.",
        "full_description": f"The {name_clean.title()} possesses well-developed biological adaptations that allow it to thrive in diverse environments. From its specialized anatomy to complex social or foraging behavior, it represents one of nature's most intriguing creatures.",
        "descriptions": [
            f"Taxonomically categorized under {category}, the {name_clean.title()} exhibits distinct morphological traits that distinguish it from related species.",
            f"In its natural habitat, the {name_clean.title()} demonstrates sophisticated territorial awareness, foraging routines, and environmental resilience.",
            f"Conservation efforts and wildlife research highlight the vital role {name_clean.title()} populations play in healthy ecological food webs."
        ],
        "appearance_description": f"Features a streamlined, robust body with distinctive coloration, protective outer covering, and keen sensory features optimized for survival.",
        "habitat_description": f"Prefers dense forest cover, open woodlands, or aquatic margins with ample food sources and clean water access.",
        "diet_description": f"Consistently feeds according to its {diet_type_default.lower()} classification, utilizing acute senses to locate and consume nutritious food.",
        "sound_description": f"Communicates through a variety of vocalizations, warning calls, or resonance sounds to coordinate with group members and mark territory.",
        "body_parts_description": f"Equipped with specialized limbs, sensory antennae or keen eyes, strong jaw structure, and protective skin or fur.",
        "life_cycle_description": f"Undergoes well-documented juvenile growth phases with dedicated parental care before maturing into a self-sufficient adult.",
        "adaptations_description": f"Possesses physiological thermoregulation, camouflaged coloration, and acute reflexes suited to its native climate.",
        "offspring_description": f"Offspring are born or hatched in secure nests or dens, receiving vital protection and nourishment during early stages.",
        "diet_type": diet_type_default,
        "lifespan": "12 - 18 years in the wild",
        "size_weight": "Average height/length: 1.2 - 1.8 m | Weight: 40 - 120 kg",
        "movement_type": movement_type_default,
        "interesting_facts": [
            f"The {name_clean.title()} has specialized sensory organs that detect subtle environmental shifts.",
            f"It can navigate complex terrain with impressive agility and speed.",
            f"Social groups often exhibit cooperative communication and protective instincts.",
            f"It plays a fundamental role in seed dispersal or balancing prey populations."
        ],
        "language": "English",
        "is_active": True
    }

    for fk, iu in species_imgs.items():
        ai_json.setdefault(fk, iu)

    return serialize_doc(ai_json)

@router.post("/generate-content")
async def generate_animal_content_route(
    req: AnimalExplorerGenerateRequest,
    current_admin: dict = Depends(require_permission("Animal Explorer", "create"))
):
    """Auto-generate comprehensive zoological content & animal characteristics images for a species using AI."""
    name_clean = req.name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Animal or species name is required")

    data = await generate_animal_data_ai(name_clean, req.category)
    return data


# --- DYNAMIC PARAMETER ROUTES (defined after specific static routes) ---

@router.get("/{item_id}", response_model=AnimalExplorerResponse)
async def get_animal_entity(item_id: str, current_admin: dict = Depends(require_permission("Animal Explorer", "read"))):
    """Get single Animal Explorer entity by ID (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    doc = await db.animal_explorer.find_one({"_id": ObjectId(item_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Animal entity not found")

    return serialize_doc(doc)

@router.put("/{item_id}", response_model=AnimalExplorerResponse)
async def update_animal_entity(item_id: str, update_data: AnimalExplorerUpdate, current_admin: dict = Depends(require_permission("Animal Explorer", "update"))):
    """Update an existing Animal Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    fields = {k: v for k, v in update_data.model_dump(exclude_unset=True).items()}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    fields["updated_at"] = datetime.now(timezone.utc)

    result = await db.animal_explorer.update_one(
        {"_id": ObjectId(item_id)},
        {"$set": fields}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Animal entity not found")

    updated = await db.animal_explorer.find_one({"_id": ObjectId(item_id)})
    return serialize_doc(updated)

@router.delete("/{item_id}")
async def delete_animal_entity(item_id: str, current_admin: dict = Depends(require_permission("Animal Explorer", "delete"))):
    """Delete an Animal Explorer entity (Requires Admin Authentication)"""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.animal_explorer.delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Animal entity not found")

    return {"message": "Animal entity deleted successfully", "id": item_id}
