from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query
from app.core.database import db

router = APIRouter(prefix="/explorer", tags=["Explorer - User Unified API"])

def serialize_doc(doc, explorer_type: str):
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    doc["explorer_type"] = explorer_type
    if "gallery_images" not in doc or doc["gallery_images"] is None:
        doc["gallery_images"] = []
    if "descriptions" not in doc or doc["descriptions"] is None:
        doc["descriptions"] = [doc.get("full_description")] if doc.get("full_description") else []
    return doc

@router.get("", response_model=Dict[str, Any])
async def get_explorer_data(
    type: Optional[str] = Query("all", description="Explorer type filter: 'space', 'ocean', 'plant', or 'all'")
):
    """
    Unified User Explorer API.
    Returns explorer items grouped by category or filtered by specified type ('space', 'ocean', 'plant', 'all').
    """
    selected_type = (type or "all").lower().strip()
    result = {
        "status": "success",
        "type": selected_type,
        "data": {}
    }

    if selected_type in ["space", "all"]:
        cursor = db.space_explorer.find({"is_active": True}).sort("order", 1)
        space_docs = await cursor.to_list(length=None)
        result["data"]["space"] = [serialize_doc(doc, "space") for doc in space_docs]

    if selected_type in ["ocean", "all"]:
        cursor = db.ocean_explorer.find({"is_active": True}).sort("order", 1)
        ocean_docs = await cursor.to_list(length=None)
        result["data"]["ocean"] = [serialize_doc(doc, "ocean") for doc in ocean_docs]

    if selected_type in ["plant", "all"]:
        cursor = db.plant_explorer.find({"is_active": True}).sort("order", 1)
        plant_docs = await cursor.to_list(length=None)
        result["data"]["plant"] = [serialize_doc(doc, "plant") for doc in plant_docs]

    return result
