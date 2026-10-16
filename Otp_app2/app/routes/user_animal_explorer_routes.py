from typing import List
from fastapi import APIRouter
from app.core.database import db
from app.models.explorer_models import AnimalExplorerResponse

router = APIRouter(prefix="/animal-explorer", tags=["Animal Explorer - User"])

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

@router.get("", response_model=List[AnimalExplorerResponse])
async def get_active_animal_entities():
    """Get all active animal entities for students & app users ordered by order number"""
    cursor = db.animal_explorer.find({"is_active": True}).sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]
