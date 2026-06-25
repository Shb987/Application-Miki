from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List
from app.core.database import db
from app.models.social_models import SocialContentInDB, ContentInteraction
from app.services.social_analytics_service import process_content_interaction
import uuid

router = APIRouter()

class InteractionRequest(BaseModel):
    content_id: str
    interaction_type: str # 'like' or 'view'

@router.get("/feed", response_model=List[SocialContentInDB])
async def get_social_feed(student_id: str):
    # Fetch student profile to get age/class
    student = await db.students.find_one({"_id": student_id})
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
        
    cursor = db.social_content.find(query).sort("created_at", -1).limit(50)
    contents = await cursor.to_list(length=50)
    return contents

@router.post("/interact")
async def interact_with_content(
    student_id: str, 
    request: InteractionRequest, 
    background_tasks: BackgroundTasks
):
    content = await db.social_content.find_one({"_id": request.content_id})
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
        
    interaction = ContentInteraction(
        student_id=student_id,
        content_id=request.content_id,
        interaction_type=request.interaction_type,
        skill_tags=content.get("skill_tags", [])
    )
    
    interaction_dict = interaction.model_dump()
    interaction_dict["_id"] = str(uuid.uuid4())
    
    # Store the interaction
    await db.content_interactions.insert_one(interaction_dict)
    
    # Update content counters
    if request.interaction_type == "like":
        await db.social_content.update_one({"_id": request.content_id}, {"$inc": {"likes_count": 1}})
    elif request.interaction_type == "view":
        await db.social_content.update_one({"_id": request.content_id}, {"$inc": {"views_count": 1}})
        
    # Queue background task for analytics to extract passion/interest
    background_tasks.add_task(process_content_interaction, student_id, interaction.skill_tags)
    
    return {"message": f"Interaction {request.interaction_type} recorded successfully"}
