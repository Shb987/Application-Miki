from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from app.utils.user_auth import get_current_user

from app.models.maths_game_models import (
    StartGameRequest,
    StartGameResponse,
    SubmitGameRequest,
    SubmitGameResponse,
    MathOperationEnum
)
from app.services.maths_game_service import MathsGameService

router = APIRouter()

def extract_user_info(current_user: dict) -> tuple[str, str]:
    """Helper to extract user_id and user_name from token."""
    user_id = current_user.get("sub") or current_user.get("user_id") or current_user.get("_id") or current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized - User ID not found in token")
        
    user_name = (
        current_user.get("name") or 
        current_user.get("full_name") or 
        current_user.get("username") or 
        current_user.get("email", "Player").split("@")[0]
    )
    return str(user_id), str(user_name)

# ============================================================================
# 2 GET ENDPOINTS
# ============================================================================

@router.get("/grades", response_model=Dict[str, Any])
async def get_supported_grades(current_user: dict = Depends(get_current_user)):
    """
    GET 1: Get list of supported class/grade levels (1-12) and operations.
    """
    return {
        "grades": list(range(1, 13)),
        "operations": [op.value for op in MathOperationEnum],
        "descriptions": {
            "grades_1_2": "Addition & Subtraction (1-20), Multiplication (1-5), Simple Division",
            "grades_3_5": "Numbers up to 500, 2-digit factors, exact division",
            "grades_6_8": "Numbers up to 1500, factors up to 30, exact division",
            "grades_9_12": "Large numbers, signed arithmetic, advanced mental arithmetic"
        }
    }

@router.get("/session/{session_id}", response_model=Dict[str, Any])
async def get_game_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    GET 2: Get game session status, room details, questions, or match results.
    """
    result = await MathsGameService.get_session(session_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

# ============================================================================
# 2 POST ENDPOINTS
# ============================================================================

@router.post("/start", response_model=StartGameResponse)
async def start_game(
    payload: StartGameRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    POST 1: Start a Game (Solo, Create Multiplayer Room, or Join Room using Token).
    - Solo: set mode="solo"
    - Create Multiplayer: set mode="multiplayer"
    - Join Multiplayer: set mode="multiplayer" and provide token="XYZ123"
    """
    user_id, user_name = extract_user_info(current_user)
    
    result = await MathsGameService.start_game(
        user_id=user_id,
        user_name=user_name,
        mode=payload.mode,
        grade=payload.grade,
        operations=payload.operations,
        num_questions=payload.num_questions,
        token=payload.token
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

@router.post("/submit", response_model=SubmitGameResponse)
async def submit_game(
    payload: SubmitGameRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    POST 2: Submit player answers for Solo or Multiplayer game. Calculates score & winner.
    """
    user_id, _ = extract_user_info(current_user)
    
    answers_data = [a.model_dump() for a in payload.answers]
    result = await MathsGameService.submit_game(
        session_id=payload.session_id,
        user_id=user_id,
        answers=answers_data,
        total_time_seconds=payload.total_time_seconds or 0.0
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result
