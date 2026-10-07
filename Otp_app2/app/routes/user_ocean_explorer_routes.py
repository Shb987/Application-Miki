from typing import List
from fastapi import APIRouter
from app.core.database import db
from app.models.explorer_models import OceanExplorerResponse

router = APIRouter(prefix="/ocean-explorer", tags=["Ocean Explorer - User"])

def serialize_doc(doc):
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    
    # Images & Aliases
    img = doc.get("title_image_url") or doc.get("image_url") or ""
    doc["title_image_url"] = img
    doc["image_url"] = img

    cover = doc.get("cover_image_url") or doc.get("banner_image_url") or ""
    doc["cover_image_url"] = cover
    doc["banner_image_url"] = cover

    # Overview & Descriptions
    overview = doc.get("overview") or doc.get("full_description") or ""
    doc["overview"] = overview
    doc["full_description"] = overview

    # Species & Image
    spec = doc.get("key_species") or doc.get("species") or ""
    doc["key_species"] = spec
    doc["species"] = spec

    spec_img = doc.get("key_species_image_url") or doc.get("species_image_url") or ""
    doc["key_species_image_url"] = spec_img
    doc["species_image_url"] = spec_img

    if "gallery_images" not in doc or doc["gallery_images"] is None:
        doc["gallery_images"] = []
    if "descriptions" not in doc or doc["descriptions"] is None:
        doc["descriptions"] = [overview] if overview else []
    if "description_images" not in doc or doc["description_images"] is None:
        doc["description_images"] = []
    return doc

@router.get("", response_model=List[OceanExplorerResponse])
async def get_active_ocean_entities():
    """Get active ocean entities for students & app users ordered by order number"""
    cursor = db.ocean_explorer.find({"is_active": True}).sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]
