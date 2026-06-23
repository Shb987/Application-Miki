from fastapi import APIRouter
from typing import List
from app.core.database import db

router = APIRouter()

@router.get("/schools", response_model=List[dict])
async def get_active_schools():
    schools = await db.schools.find({"status": "active"}).to_list(length=None)
    result = []
    for s in schools:
        result.append({
            "id": str(s["_id"]),
            "name": s.get("name"),
            "place_code": s.get("place_code"),
            "link": s.get("link")
        })
    return result
