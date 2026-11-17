from typing import List
from fastapi import APIRouter
from app.core.database import db
from app.models.explorer_models import AnimalExplorerResponse

router = APIRouter(prefix="/animal-explorer", tags=["Animal Explorer - User"])

DEFAULT_ANIMAL_CATEGORIES = [
    {"name": "Wild Animals", "image_url": "https://images.unsplash.com/photo-1546182990-dffeafbe841d?auto=format&fit=crop&w=800&q=80"},
    {"name": "Domestic Animals & Pets", "image_url": "https://images.unsplash.com/photo-1543466835-00a7907e9de1?auto=format&fit=crop&w=800&q=80"},
    {"name": "Insects", "image_url": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?auto=format&fit=crop&w=800&q=80"},
    {"name": "Reptiles", "image_url": "https://images.unsplash.com/photo-1504450874802-0ba2bcd9b5ae?auto=format&fit=crop&w=800&q=80"},
    {"name": "Mammals", "image_url": "https://images.unsplash.com/photo-1557050543-4d5f4e07ef46?auto=format&fit=crop&w=800&q=80"},
    {"name": "Birds", "image_url": "https://images.unsplash.com/photo-1444464666168-49d633b86797?auto=format&fit=crop&w=800&q=80"},
    {"name": "Amphibians", "image_url": "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?auto=format&fit=crop&w=800&q=80"},
    {"name": "Aquatic & Marine Animals", "image_url": "https://images.unsplash.com/photo-1544551763-46a013bb70d5?auto=format&fit=crop&w=800&q=80"},
    {"name": "Endangered Animals", "image_url": "https://images.unsplash.com/photo-1564349683136-77e08dba1ef7?auto=format&fit=crop&w=800&q=80"},
    {"name": "Prehistoric Animals", "image_url": "https://images.unsplash.com/photo-1570481662006-a3a1374699e8?auto=format&fit=crop&w=800&q=80"},
    {"name": "Arachnids", "image_url": "https://images.unsplash.com/photo-1522069169874-c58ec4b76be5?auto=format&fit=crop&w=800&q=80"},
    {"name": "Worms & Other Invertebrates", "image_url": "https://images.unsplash.com/photo-1508873696983-2df57036476b?auto=format&fit=crop&w=800&q=80"}
]

def serialize_doc(doc, cat_image_map=None):
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

    # If primary category exists and is not in categories, ensure it's included
    primary_c = doc.get("category")
    if primary_c and primary_c not in doc["categories"]:
        doc["categories"].insert(0, primary_c)

    if not doc.get("category") and doc.get("categories"):
        doc["category"] = doc["categories"][0]

    primary_c = doc.get("category", "Wild Animals")
    if cat_image_map and primary_c in cat_image_map:
        doc["category_image_url"] = cat_image_map[primary_c]
    elif not doc.get("category_image_url"):
        doc["category_image_url"] = next((c["image_url"] for c in DEFAULT_ANIMAL_CATEGORIES if c["name"] == primary_c), "")

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
    """
    Get all active animal explorer entities (parameter-free endpoint).
    When an animal belongs to multiple categories simultaneously (assigned to multiple categories),
    the same animal is included in each category it is assigned to, with that category's specific uploaded image.
    Preserves all animal fields and complete data across all categories.
    """
    stored_cats = await db.animal_categories.find().to_list(100)
    cat_image_map = {c["name"]: c.get("image_url", "") for c in DEFAULT_ANIMAL_CATEGORIES}
    for sc in stored_cats:
        if sc.get("image_url"):
            cat_image_map[sc["name"]] = sc["image_url"]

    # Canonical category order: defaults first, then any extra custom categories
    ordered_category_names = [c["name"] for c in DEFAULT_ANIMAL_CATEGORIES]
    for sc in stored_cats:
        c_name = sc.get("name")
        if c_name and c_name not in ordered_category_names:
            ordered_category_names.append(c_name)

    cursor = db.animal_explorer.find({"is_active": True}).sort("order", 1)
    entities = await cursor.to_list(length=None)

    serialized_entities = [serialize_doc(doc, cat_image_map) for doc in entities]

    results = []
    # Grouped/expanded by category in canonical category order, preserving animal display order within each category
    for c_name in ordered_category_names:
        for item in serialized_entities:
            item_cats = item.get("categories") or ([item.get("category")] if item.get("category") else ["Wild Animals"])
            if c_name in item_cats or item.get("category") == c_name:
                entry = dict(item)
                entry["category"] = c_name
                entry["category_image_url"] = cat_image_map.get(
                    c_name,
                    next((c["image_url"] for c in DEFAULT_ANIMAL_CATEGORIES if c["name"] == c_name), item.get("category_image_url", ""))
                )
                results.append(entry)

    # In case an animal has an assigned category not in ordered_category_names
    for item in serialized_entities:
        item_cats = item.get("categories") or ([item.get("category")] if item.get("category") else ["Wild Animals"])
        for extra_c in item_cats:
            if extra_c and extra_c not in ordered_category_names:
                entry = dict(item)
                entry["category"] = extra_c
                entry["category_image_url"] = cat_image_map.get(extra_c, item.get("category_image_url", ""))
                results.append(entry)

    return results
