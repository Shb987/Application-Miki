from fastapi import APIRouter, HTTPException, Depends
from app.core.database import db
from app.models.special_day_models import SpecialDayResponse
from app.utils.user_auth import get_current_user
from datetime import datetime, timezone

router = APIRouter(prefix="/special-day", tags=["Special Days - User"])

def serialize_doc(doc):
    if not doc: return None
    doc["id"] = str(doc.pop("_id"))
    return doc

@router.get("/today", response_model=SpecialDayResponse)
async def get_today_special_day(current_user: dict = Depends(get_current_user)):
    """Get the special day for today (Server Time)"""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Find active special day for today
    day = await db.special_days.find_one({"date": today_str, "is_active": True})
    
    if not day:
        # 404 is appropriate here, frontend can show default/nothing
        raise HTTPException(status_code=404, detail="No special day configured for today")
        
    return serialize_doc(day)
