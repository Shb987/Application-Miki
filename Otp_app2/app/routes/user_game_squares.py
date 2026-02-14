from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional
from app.utils.user_auth import get_current_user
from app.services.squares_service import SquaresService
from app.models.squares_models import (
    SquaresLevelsResponse,
    SquaresSessionResponse,
    SquaresWordSubmission,
    SquaresWordResponse
)

router = APIRouter(prefix="/squares")

@router.get("/levels", response_model=SquaresLevelsResponse)
async def get_levels(student_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch level list status for a student"""
    result = await SquaresService.get_available_levels(student_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.post("/start", response_model=SquaresSessionResponse)
async def start_game(student_id: str, level: int = Query(..., description="Level to start"), current_user: dict = Depends(get_current_user)):
    """Start or resume a specific level"""
    result = await SquaresService.start_game(student_id, level)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.post("/submit", response_model=SquaresWordResponse)
async def submit_word(payload: SquaresWordSubmission, current_user: dict = Depends(get_current_user)):
    """Submit a word for the active session"""
    result = await SquaresService.process_words(payload.session_id, payload.words)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/status", response_model=Dict[str, Any])
async def get_status(student_id: str, current_user: dict = Depends(get_current_user)):
    """Get active session status for a student"""
    result = await SquaresService.get_status(student_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
