from typing import List
from fastapi import APIRouter
from app.core.database import db
from app.models.explorer_models import PlantExplorerResponse

router = APIRouter(prefix="/plant-explorer", tags=["Plant Explorer - User"])

def serialize_doc(doc):
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    if "gallery_images" not in doc or doc["gallery_images"] is None:
        doc["gallery_images"] = []
    if "descriptions" not in doc or doc["descriptions"] is None:
        doc["descriptions"] = [doc.get("full_description")] if doc.get("full_description") else []
    return doc

@router.get("", response_model=List[PlantExplorerResponse])
async def get_active_plant_entities():
    """Get active plant entities for students & app users ordered by order number"""
    cursor = db.plant_explorer.find({"is_active": True}).sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]
