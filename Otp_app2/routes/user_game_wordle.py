from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional
from utils.user_auth import get_current_user

from services.wordle_service import WordleService
from models.wordle_models import (
    WordleGuessRequest,
    WordleGuessResponse,
    WordleSessionResponse,
    WordleLevelsResponse
)

router = APIRouter(prefix="/wordle")

@router.get("/levels", response_model=WordleLevelsResponse)
async def get_available_levels(student_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of all levels with their status (locked/unlocked/completed).
    """
    result = await WordleService.get_available_levels(student_id)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@router.post("/start", response_model=WordleSessionResponse)
async def start_wordle_game(
    student_id: str,
    selected_level: Optional[int] = Query(None, description="Optional: Select a specific level to play (practice mode)"),
    current_user: dict = Depends(get_current_user)
    
):
    """
    Starts a new Wordle game for a student.
    If selected_level is provided, starts in practice mode for that level.
    Otherwise, starts in progression mode at the student's current level.
    """
    result = await WordleService.start_game(student_id, selected_level)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result

@router.post("/guess", response_model=WordleGuessResponse)
async def submit_guess(payload: WordleGuessRequest,
    current_user: dict = Depends(get_current_user)
    ):
    """
    Submit a guess for an active Wordle session.
    """
    result = await WordleService.process_guess(
        session_id=payload.session_id,
        guess=payload.guess
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
@router.get("/status", response_model=Dict[str, Any])
async def get_wordle_status(student_id: str,
    current_user: dict = Depends(get_current_user)
    ):
    """
    Get current active Wordle session for a student.
    """
    result = await WordleService.get_status(student_id)
    return result