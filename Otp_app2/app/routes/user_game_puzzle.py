from fastapi import APIRouter, HTTPException, Depends, Query
from app.utils.user_auth import get_current_user
from app.services.puzzle_service import PuzzleService
from app.models.puzzle_models import (
    PuzzleLevelsResponse,
    PuzzleStartRequest,
    PuzzleStartResponse,
    PuzzleCompleteRequest,
    PuzzleCompleteResponse
)

router = APIRouter(prefix="/puzzle", tags=["Games - Puzzle"])

@router.get("/levels", response_model=PuzzleLevelsResponse)
async def get_puzzle_levels(
    student_id: str, 
    current_user: dict = Depends(get_current_user)
):
    """
    Get the list of puzzle levels available for the student's class range difficulty.
    Returns level lock/unlock status.
    """
    result = await PuzzleService.get_available_levels(student_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.post("/start", response_model=PuzzleStartResponse)
async def start_puzzle_game(
    payload: PuzzleStartRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch the puzzle configuration (image_url, grid_size) for a specific level.
    Used by Flutter to render the local puzzle game.
    """
    result = await PuzzleService.start_game(payload.student_id, payload.level)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.post("/complete", response_model=PuzzleCompleteResponse)
async def complete_puzzle_level(
    payload: PuzzleCompleteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Called when the student successfully completes the puzzle locally in Flutter.
    Marks the level as completed and unlocks the next one if applicable.
    """
    result = await PuzzleService.complete_level(payload.student_id, payload.level)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
