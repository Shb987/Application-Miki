from fastapi import APIRouter, HTTPException
from typing import List, Optional
from app.core.database import db
from app.models.tutorial_models import TutorialModule

router = APIRouter(prefix="/user/tutorials")

@router.get("/")
async def get_user_tutorials(
    student_class: str,
    board: Optional[str] = None
):
    """
    Get tutorials for a specific class and optional board (NCERT/SCERT)
    """
    query = {"student_class": student_class}
    if board:
        query["board"] = board

        
    cursor = db.tutorials.find(query)
    tutorials = await cursor.to_list(length=100)
    
    # Convert ObjectId to str
    for t in tutorials:
        t["_id"] = str(t["_id"])
        
    return tutorials
