from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel
from typing import List, Dict, Any
from app.core.database import db
from app.models.social_models import SocialContentInDB, ContentInteraction
from app.services.social_analytics_service import process_content_interaction
from bson import ObjectId

router = APIRouter()

class InteractionRequest(BaseModel):
    content_id: str
    interaction_type: str # 'like' or 'view'

@router.get("/feed", response_model=List[Dict[str, Any]])
async def get_social_feed(
    student_id: str,
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of items to return")
):
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    # Fetch student profile to get age/class
    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
        
    student_class = student.get("student_class")
    
    # Simple query to match target_class if defined, else fallback to any
    query = {}
    if student_class:
        query["$or"] = [
            {"target_class": student_class},
            {"target_class": None}
        ]
        
    cursor = db.social_content.find(query).sort("created_at", -1).skip(skip).limit(limit)
    contents = await cursor.to_list(length=limit)
    
    # Convert ObjectId to string for all content items
    for c in contents:
        c["_id"] = str(c["_id"])

    # --- Batch check which content items this student has already liked ---
    content_ids = [c["_id"] for c in contents]
    
    liked_cursor = db.content_interactions.find(
        {
            "student_id": student_id,
            "content_id": {"$in": content_ids},
            "interaction_type": "like"
        },
        {"content_id": 1, "_id": 0}  # Only fetch content_id field
    )
    liked_docs = await liked_cursor.to_list(length=len(content_ids))
    
    # Build a set of liked content IDs for O(1) lookup
    liked_content_ids = {doc["content_id"] for doc in liked_docs}
    
    # Attach is_liked flag to each content item
    for c in contents:
        c["is_liked"] = c["_id"] in liked_content_ids
    # --------------------------------------------------------------------

    return contents

@router.post("/interact")
async def interact_with_content(
    student_id: str, 
    request: InteractionRequest, 
    background_tasks: BackgroundTasks
):
    try:
        content_oid = ObjectId(request.content_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid content_id format")

    content = await db.social_content.find_one({"_id": content_oid})
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
        
    interaction = ContentInteraction(
        student_id=student_id,
        content_id=request.content_id,
        interaction_type=request.interaction_type,
        skill_tags=content.get("skill_tags", [])
    )
    
    interaction_dict = interaction.model_dump()
    
    # Store the interaction
    await db.content_interactions.insert_one(interaction_dict)
    
    # Update content counters
    if request.interaction_type == "like":
        await db.social_content.update_one({"_id": content_oid}, {"$inc": {"likes_count": 1}})
    elif request.interaction_type == "view":
        await db.social_content.update_one({"_id": content_oid}, {"$inc": {"views_count": 1}})
        
    # Queue background task for analytics to extract passion/interest
    background_tasks.add_task(process_content_interaction, student_id, interaction.skill_tags)
    
    return {"message": f"Interaction {request.interaction_type} recorded successfully"}
