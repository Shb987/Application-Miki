from typing import List, Optional
from fastapi import APIRouter, Query
from app.core.database import db
from app.models.explorer_models import AnimalExplorerResponse, AnimalCategoryResponse
from app.routes.admin_animal_explorer_routes import DEFAULT_ANIMAL_CATEGORIES

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

@router.get("/categories", response_model=List[AnimalCategoryResponse])
async def get_active_categories():
    """Get all animal categories with image URLs and active animal count for students."""
    pipeline = [{"$match": {"is_active": True}}, {"$group": {"_id": "$category", "count": {"$sum": 1}}}]
    counts_cursor = db.animal_explorer.aggregate(pipeline)
    counts_list = await counts_cursor.to_list(length=100)
    counts_map = {item["_id"]: item["count"] for item in counts_list if item.get("_id")}

    stored_cursor = db.animal_categories.find()
    stored_list = await stored_cursor.to_list(length=100)
    stored_map = {item["name"]: item for item in stored_list if item.get("name")}

    categories = []
    for default_cat in DEFAULT_ANIMAL_CATEGORIES:
        c_name = default_cat["name"]
        stored = stored_map.get(c_name, {})
        cat_obj = {
            "name": c_name,
            "image_url": stored.get("image_url") or default_cat["image_url"],
            "order": stored.get("order") or default_cat["order"],
            "description": stored.get("description") or default_cat["description"],
            "count": counts_map.get(c_name, 0)
        }
        categories.append(cat_obj)

    for c_name, stored in stored_map.items():
        if not any(c["name"] == c_name for c in categories):
            categories.append({
                "name": c_name,
                "image_url": stored.get("image_url", ""),
                "order": stored.get("order", len(categories) + 1),
                "description": stored.get("description", ""),
                "count": counts_map.get(c_name, 0)
            })

    categories.sort(key=lambda x: x["order"])
    return categories

@router.get("", response_model=List[AnimalExplorerResponse])
async def get_active_animal_entities(category: Optional[str] = Query(None, description="Filter by category name")):
    """Get all active animal entities for students & app users ordered by order number"""
    query = {"is_active": True}
    if category and category.strip() and category.strip().lower() != "all":
        query["category"] = category.strip()

    cursor = db.animal_explorer.find(query).sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]
