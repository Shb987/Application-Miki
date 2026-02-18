from fastapi import APIRouter, HTTPException, Depends, Query, Body
from app.core.database import db
from app.models.special_day_models import SpecialDayCreate, SpecialDayUpdate, SpecialDayResponse
from app.utils.user_auth import get_current_user # Assuming admin auth is similar or handled here
from bson import ObjectId
from datetime import datetime, timezone
import pytz
from app.services.scheduler_service import check_and_notify_special_days

router = APIRouter(prefix="/special-days", tags=["Special Days - Admin"])

def serialize_doc(doc):
    if not doc: return None
    doc["id"] = str(doc.pop("_id"))
    return doc

@router.get("/", response_model=list[SpecialDayResponse])
async def get_all_special_days(
    limit: int = 50, 
    skip: int = 0
):
    """List all special days, sorted by date (descending)"""
    cursor = db.special_days.find().sort("date", -1).skip(skip).limit(limit)
    days = await cursor.to_list(length=limit)
    return [serialize_doc(day) for day in days]

@router.post("/", response_model=SpecialDayResponse)
async def create_special_day(day_data: SpecialDayCreate):
    """Create a new manual special day"""
    # 1. Check for duplicate date
    existing = await db.special_days.find_one({"date": day_data.date})
    if existing:
        raise HTTPException(status_code=400, detail=f"A special day for {day_data.date} already exists.")

    # 2. Insert
    new_day = day_data.model_dump()
    new_day["created_at"] = datetime.now(timezone.utc)
    
    result = await db.special_days.insert_one(new_day)
    
    # 3. Trigger immediate notification if the date is TODAY
    tz = pytz.timezone("Asia/Kolkata")
    today_ist = datetime.now(tz).strftime("%Y-%m-%d")
    if day_data.date == today_ist:
        # We don't await this to keep the API responsive, 
        # or we can await it if we want to ensure it sent before returning.
        # Given it's a broadcast, better to fire it in background.
        import asyncio
        asyncio.create_task(check_and_notify_special_days(db))

    # 4. Return created
    created = await db.special_days.find_one({"_id": result.inserted_id})
    return serialize_doc(created)

@router.put("/{day_id}", response_model=SpecialDayResponse)
async def update_special_day(day_id: str, update_data: SpecialDayUpdate):
    """Update an existing special day"""
    if not ObjectId.is_valid(day_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    # Filter out None values
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    result = await db.special_days.update_one(
        {"_id": ObjectId(day_id)},
        {"$set": update_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Special Day not found")

    # 3. Trigger immediate notification if the date is TODAY
    updated_doc = await db.special_days.find_one({"_id": ObjectId(day_id)})
    tz = pytz.timezone("Asia/Kolkata")
    today_ist = datetime.now(tz).strftime("%Y-%m-%d")
    
    if updated_doc.get("date") == today_ist:
        import asyncio
        asyncio.create_task(check_and_notify_special_days(db))

    return serialize_doc(updated_doc)

@router.delete("/{day_id}")
async def delete_special_day(day_id: str):
    """Delete a special day"""
    if not ObjectId.is_valid(day_id):
        raise HTTPException(status_code=400, detail="Invalid ID format")

    result = await db.special_days.delete_one({"_id": ObjectId(day_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Special Day not found")
        
    return {"message": "Special Day deleted successfully"}
