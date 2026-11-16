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

    # Ensure categories list is cleanly serialized
    cats = doc.get("categories")
    if not cats:
        primary_cat = doc.get("category", "Wild Animals")
        doc["categories"] = [primary_cat] if primary_cat else ["Wild Animals"]
    elif isinstance(cats, str):
        doc["categories"] = [c.strip() for c in cats.split(",") if c.strip()]
    elif isinstance(cats, list):
        doc["categories"] = [str(c).strip() for c in cats if str(c).strip()]

    if not doc.get("category") and doc.get("categories"):
        doc["category"] = doc["categories"][0]

    str_fields = [
        "category_image_url",
        "scientific_name", "family", "habitat",
        "climate_zone", "conservation_status", "fun_fact", "short_summary",
        "short_description", "full_description", "image_url", "banner_image_url",
        "appearance_image_url", "appearance_description",
        "habitat_image_url", "habitat_description",
        "diet_image_url", "diet_description",
        "body_parts_image_url", "body_parts_description",
        "life_cycle_image_url", "life_cycle_description",
        "adaptations_image_url", "adaptations_description",
        "offspring_image_url", "offspring_description",
        "diet_type", "lifespan", "size_weight", "movement_type", "language"
    ]
    for k in str_fields:
        if k not in doc or doc[k] is None:
            doc[k] = ""

    doc.pop("sound_audio_url", None)
    doc.pop("sound_image_url", None)
    doc.pop("sound_description", None)
    return doc

@router.get("", response_model=List[AnimalExplorerResponse])
async def get_active_animal_entities():
    """Get all active animal explorer entities ordered by order number (Parameter-free single GET endpoint)"""
    cursor = db.animal_explorer.find({"is_active": True}).sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]
