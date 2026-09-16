from typing import List
from app.core.database import db
from app.models.space_explorer_models import SpaceExplorerResponse
from fastapi import APIRouter

router = APIRouter(prefix="/space-explorer", tags=["Space Explorer - User"])

def serialize_doc(doc):
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    if "gallery_images" not in doc or doc["gallery_images"] is None:
        doc["gallery_images"] = []
    if "descriptions" not in doc or doc["descriptions"] is None:
        doc["descriptions"] = [doc.get("full_description")] if doc.get("full_description") else []
    return doc

@router.get("", response_model=List[SpaceExplorerResponse])
async def get_active_space_entities():
    """Get active space entities for students & app users ordered by order number (Accessible to all students)"""
    cursor = db.space_explorer.find({"is_active": True}).sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]
