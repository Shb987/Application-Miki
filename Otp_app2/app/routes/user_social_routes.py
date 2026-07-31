from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.core.database import db
from app.models.social_models import SocialContentInDB, ContentInteraction
from app.models.chat_models import SharedPostCard
from app.services.social_analytics_service import process_content_interaction
from app.services.notification_service import create_notification
from app.routes.chat_routes import manager  # WebSocket broadcast manager
from bson import ObjectId
from datetime import datetime, timezone

router = APIRouter()

class InteractionRequest(BaseModel):
    content_id: str
    interaction_type: str  # 'like', 'view', or 'share'

class ShareToGroupRequest(BaseModel):
    student_id: str
    content_id: str
    group_id: str

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
        {"content_id": 1, "_id": 0}
    )
    liked_docs = await liked_cursor.to_list(length=len(content_ids))
    
    # Build a set of liked content IDs for O(1) lookup
    liked_content_ids = {doc["content_id"] for doc in liked_docs}
    
    # Attach is_liked flag to each content item
    for c in contents:
        c["is_liked"] = c["_id"] in liked_content_ids
    # --------------------------------------------------------------------

    return contents


@router.get("/content/{content_id}", response_model=Dict[str, Any])
async def get_single_content(content_id: str, student_id: str):
    """
    Fetch a single social content item by ID.
    Used when a student taps a shared post card in group chat.
    """
    try:
        c_oid = ObjectId(content_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid content_id format")

    content = await db.social_content.find_one({"_id": c_oid})
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    content["_id"] = str(content["_id"])

    # Check if the student has already liked this post
    liked = await db.content_interactions.find_one({
        "student_id": student_id,
        "content_id": content_id,
        "interaction_type": "like"
    })
    content["is_liked"] = liked is not None

    return content


@router.post("/interact")
async def interact_with_content(
    student_id: str, 
    request: InteractionRequest, 
    background_tasks: BackgroundTasks
):
    """
    Record a student's interaction (like, view, or share) with a content item.
    """
    valid_types = {"like", "view", "share"}
    if request.interaction_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid interaction_type. Must be one of: {valid_types}")

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
    elif request.interaction_type == "share":
        await db.social_content.update_one({"_id": content_oid}, {"$inc": {"shares_count": 1}})
        
    # Queue background analytics with the correct interaction_type for weighted scoring
    background_tasks.add_task(
        process_content_interaction,
        student_id,
        interaction.skill_tags,
        request.interaction_type
    )
    
    return {"message": f"Interaction '{request.interaction_type}' recorded successfully"}


@router.post("/share-to-group")
async def share_post_to_group(
    request: ShareToGroupRequest,
    background_tasks: BackgroundTasks
):
    """
    Share a social content post directly into a community group chat.

    - Validates student is a group member
    - Embeds a SharedPostCard in chat_messages (message_type = "shared_post")
    - Broadcasts to online members via WebSocket
    - Sends push notification to offline group members via OneSignal
    - Records a 'share' interaction for analytics
    """
    # --- 1. Validate group exists and student is a member ---
    try:
        g_oid = ObjectId(request.group_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid group_id format")

    group = await db.chat_groups.find_one({"_id": g_oid, "member_ids": request.student_id})
    if not group:
        raise HTTPException(status_code=403, detail="You are not a member of this group")

    # --- 2. Validate content exists ---
    try:
        c_oid = ObjectId(request.content_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid content_id format")

    content = await db.social_content.find_one({"_id": c_oid})
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    # --- 3. Resolve contributor name ---
    contributor_name = "Unknown"
    contributor_id = content.get("contributor_id")
    if contributor_id:
        contributor = await db.contributors.find_one({"_id": contributor_id})
        if contributor:
            contributor_name = contributor.get("name", "Unknown")

    # --- 4. Resolve sharer's name ---
    try:
        s_oid = ObjectId(request.student_id)
        sharer = await db.students.find_one({"_id": s_oid})
        sharer_name = sharer.get("student_name", "A student") if sharer else "A student"
    except Exception:
        sharer_name = "A student"

    # --- 5. Build the shared post card ---
    shared_post_card = SharedPostCard(
        content_id=str(content["_id"]),
        title=content.get("title", ""),
        description=(content.get("description", ""))[:200],  # First 200 chars as preview
        media_type=content.get("media_type", "text"),
        media_url=content.get("media_url"),
        skill_tags=content.get("skill_tags", []),
        contributor_name=contributor_name
    )

    # --- 6. Build the chat message document ---
    group_id_str = str(request.group_id)
    now = datetime.now(timezone.utc)

    msg_doc = {
        "group_id": group_id_str,
        "sender_id": request.student_id,
        "sender_name": sharer_name,
        "message": f"{sharer_name} shared a post: {content.get('title', '')}",
        "message_type": "shared_post",
        "shared_post": shared_post_card.model_dump(),
        "timestamp": now
    }

    # --- 7. Persist the message ---
    result = await db.chat_messages.insert_one(msg_doc)
    msg_doc["_id"] = str(result.inserted_id)
    msg_doc["timestamp"] = now.isoformat()

    # --- 8. Broadcast to all ONLINE group members via WebSocket ---
    await manager.broadcast_to_group(group_id_str, msg_doc)

    # --- 9. Increment shares_count on the content document ---
    await db.social_content.update_one({"_id": c_oid}, {"$inc": {"shares_count": 1}})

    # --- 10. Record share interaction for analytics ---
    interaction = ContentInteraction(
        student_id=request.student_id,
        content_id=request.content_id,
        interaction_type="share",
        skill_tags=content.get("skill_tags", [])
    )
    await db.content_interactions.insert_one(interaction.model_dump())

    # Weighted analytics update (share = +3)
    background_tasks.add_task(
        process_content_interaction,
        request.student_id,
        interaction.skill_tags,
        "share"
    )

    # --- 11. Notify OFFLINE group members (everyone except the sharer) ---
    group_name = group.get("name", "your group")
    member_ids = group.get("member_ids", [])
    online_ids = set(manager.active_connections.get(group_id_str, {}).keys())

    for member_id in member_ids:
        if member_id == request.student_id:
            continue  # Don't notify the sharer themselves
        if member_id in online_ids:
            continue  # Already received it via WebSocket

        # Fire push notification to offline member
        background_tasks.add_task(
            create_notification,
            db,
            member_id,
            "New Post Shared",
            f"{sharer_name} shared a post in '{group_name}'",
            "social_share",
            {
                "group_id": group_id_str,
                "content_id": request.content_id,
                "shared_post": shared_post_card.model_dump()
            }
        )

    return {
        "message": "Post shared successfully to group",
        "group_id": group_id_str,
        "content_id": request.content_id,
        "shares_count_updated": True
    }


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
