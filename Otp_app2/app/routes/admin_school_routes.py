from fastapi import APIRouter, HTTPException, Depends
from typing import List
from bson import ObjectId
from app.core.database import db
from app.models.school_models import SchoolCreate, SchoolUpdate, SchoolInDB
from fastapi.encoders import jsonable_encoder
from app.utils.admin_auth import require_permission

router = APIRouter()

@router.post("/schools", response_model=dict)
async def create_school(school: SchoolCreate, current_admin: dict = Depends(require_permission("Schools", "create"))):
    school_dict = school.model_dump()
    school_db = SchoolInDB(**school_dict)
    
    # Check if link already exists
    existing = await db.schools.find_one({"link": school.link})
    if existing:
        raise HTTPException(status_code=400, detail="School with this link already exists")
    
    result = await db.schools.insert_one(jsonable_encoder(school_db))
    return {"message": "School created successfully", "id": str(result.inserted_id)}

@router.get("/schools", response_model=dict)
async def get_schools(current_admin: dict = Depends(require_permission("Schools", "read"))):
    schools = await db.schools.find().to_list(length=None)
    for s in schools:
        s["_id"] = str(s["_id"])
    return {"data": schools}

@router.get("/schools/{school_id}", response_model=dict)
async def get_school(school_id: str, current_admin: dict = Depends(require_permission("Schools", "read"))):
    try:
        obj_id = ObjectId(school_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid school ID")
    
    school = await db.schools.find_one({"_id": obj_id})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    
    school["_id"] = str(school["_id"])
    return {"data": school}

@router.put("/schools/{school_id}", response_model=dict)
async def update_school(school_id: str, school_update: SchoolUpdate, current_admin: dict = Depends(require_permission("Schools", "update"))):
    # Use exclude_unset=True to only update fields that were actually sent
    update_data = school_update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
        
    try:
        obj_id = ObjectId(school_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid school ID")
        
    result = await db.schools.update_one({"_id": obj_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="School not found")
        
    return {"message": "School updated successfully"}

@router.delete("/schools/{school_id}", response_model=dict)
async def delete_school(school_id: str, current_admin: dict = Depends(require_permission("Schools", "delete"))):
    try:
        obj_id = ObjectId(school_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid school ID")
        
    result = await db.schools.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="School not found")
        
    return {"message": "School deleted successfully"}
