from typing import List, Optional
from fastapi import APIRouter, Query
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
        "category_image_url",
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
async def get_active_animal_entities(category: Optional[str] = Query(None, description="Optional category filter (e.g. Mammals, Wild Animals)")):
    """Get all active animal explorer entities ordered by order number (Single User Endpoint)"""
    query = {"is_active": True}
    if category and category.strip() and category.strip().lower() != "all":
        query["category"] = category.strip()

    cursor = db.animal_explorer.find(query).sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]
