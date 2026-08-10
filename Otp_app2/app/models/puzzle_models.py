from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class PuzzleLevelInfo(BaseModel):
    level: int
    status: str  # "locked", "unlocked", "completed"
    playable: bool
    image_url: Optional[str] = ""

class PuzzleLevelsResponse(BaseModel):
    student_id: str
    difficulty: str
    highest_level_reached: int
    total_levels: int
    levels: List[PuzzleLevelInfo]

class PuzzleStartRequest(BaseModel):
    student_id: str
    level: int

class PuzzleStartResponse(BaseModel):
    level: int
    difficulty: str
    image_url: str
    grid_size: int
    mode: str # "progression" or "practice"

class PuzzleCompleteRequest(BaseModel):
    student_id: str
    level: int

class PuzzleCompleteResponse(BaseModel):
    status: str
    message: str
    next_level_unlocked: bool
    highest_level_reached: int
