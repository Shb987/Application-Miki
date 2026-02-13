from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

class SquaresLevelInfo(BaseModel):
    level: int
    status: str  # "locked", "unlocked", "completed"
    playable: bool

class SquaresLevelsResponse(BaseModel):
    student_id: str
    class_range: str
    highest_level_reached: int
    total_levels: int
    levels: List[SquaresLevelInfo]

class SquaresSessionResponse(BaseModel):
    session_id: Optional[str] = None
    level: int
    class_range: str
    grid: List[List[str]]  # 4x4 matrix
    found_words: List[str]
    found_bonus_words: List[str]
    main_words_count: int
    bonus_words_count: int
    status: str  # "playing", "idle"
    mode: str  # "progression", "practice"

class SquaresWordSubmission(BaseModel):
    session_id: str
    word: str

class SquaresWordResponse(BaseModel):
    is_valid: bool
    is_main: bool
    is_bonus: bool
    is_new: bool
    message: str
    found_words: List[str]
    found_bonus_words: List[str]
    main_words_remaining: int
    status: str  # "playing", "level_cleared"
    level: int
    next_level_unlocked: bool
