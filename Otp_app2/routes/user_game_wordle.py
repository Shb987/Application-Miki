from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from services.wordle_service import WordleService
from models.wordle_models import (
    WordleGuessRequest,
    WordleGuessResponse,
    WordleSessionResponse
)

router = APIRouter(prefix="/wordle")

@router.post("/start", response_model=WordleSessionResponse)
async def start_wordle_game(student_id: str):
    """
    Starts a new Wordle game for a student.
    """
    result = await WordleService.start_game(student_id)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result

@router.post("/guess", response_model=WordleGuessResponse)
async def submit_guess(payload: WordleGuessRequest):
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
async def get_wordle_status(student_id: str):
    """
    Get current active Wordle session for a student.
    """
    result = await WordleService.get_status(student_id)
    return result