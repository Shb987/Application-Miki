from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from app.core.database import db
from app.models.tutorial_models import YouTubeFetchRequest, TutorialModule, VideoLink
from app.services.youtube_service import youtube_service
from app.utils.admin_auth import require_permission
from datetime import datetime

router = APIRouter(prefix="/admin/tutorials")

@router.post("/fetch-and-save")
async def fetch_and_save_youtube_links(
    request: YouTubeFetchRequest,
    current_admin: dict = Depends(require_permission("Tutorials", "create"))
):
    """
    Fetch YouTube videos from a URL (Channel or Playlist) and save to MongoDB.
    """
    try:
        extracted_id, id_type = youtube_service.extract_id(request.youtube_url)
        
        target_playlist_id = None
        if id_type == "playlist":
            target_playlist_id = extracted_id
        elif id_type == "channel":
            target_playlist_id = youtube_service.get_uploads_id(extracted_id)
        else:
            # If it's text, try to search for it as a playlist
            target_playlist_id, _ = youtube_service.search_playlist_by_name(request.youtube_url)

        if not target_playlist_id:
            raise HTTPException(status_code=400, detail="Could not determine target playlist ID from provided URL")

        # Fetch videos
        videos = youtube_service.fetch_videos(target_playlist_id)
        
        if not videos:
            return {"message": "No videos found", "count": 0}

        video_links = [VideoLink(**v) for v in videos]

        # Prepare tutorial module
        tutorial_data = TutorialModule(
            student_class=request.student_class,
            board=request.board or "NCERT",
            subject=request.subject,
            topic=request.topic,
            youtube_url=request.youtube_url,
            video_links=video_links
        )

        query = {
            "student_class": request.student_class,
            "board": request.board or "NCERT",
            "subject": request.subject,
            "topic": request.topic,
            "youtube_url": request.youtube_url
        }

        existing = await db.tutorials.find_one(query)

        if existing:
            await db.tutorials.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "video_links": [v.dict() for v in video_links],
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            message = "Tutorial updated successfully"
        else:
            result = await db.tutorials.insert_one(tutorial_data.dict())
            message = "Tutorial created successfully"

        return {
            "message": message,
            "count": len(videos),
            "playlist_id": target_playlist_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def get_tutorials(
    student_class: Optional[str] = None,
    board: Optional[str] = None,
    subject: Optional[str] = None,
    current_admin: dict = Depends(require_permission("Tutorials", "read"))
):
    """
    Get all stored tutorials.
    """
    query = {}
    if student_class:
        query["student_class"] = student_class
    if board:
        query["board"] = board
    if subject:
        query["subject"] = subject
        
    cursor = db.tutorials.find(query)
    tutorials = await cursor.to_list(length=100)
    
    # Convert ObjectId to str
    for t in tutorials:
        t["_id"] = str(t["_id"])
        
    return tutorials

@router.delete("/{tutorial_id}")
async def delete_tutorial(
    tutorial_id: str,
    current_admin: dict = Depends(require_permission("Tutorials", "delete"))
):
    """
    Delete a tutorial module.
    """
    from bson import ObjectId
    result = await db.tutorials.delete_one({"_id": ObjectId(tutorial_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tutorial not found")
    return {"message": "Tutorial deleted successfully"}
