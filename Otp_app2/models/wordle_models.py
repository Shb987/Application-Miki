from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class WordleGuessRequest(BaseModel):
    session_id: str
    guess: str

class WordleWordResult(BaseModel):
    word: str
    status: str  # "won", "lost", "skipped"
    attempts_used: int
    score_awarded: int

class WordleSessionResponse(BaseModel):
    session_id: Optional[str] = None
    current_round: int # 1 to 20
    level: int # Alias for current_round
    total_rounds: int
    current_word_length: Optional[int] = None
    revealed_pattern: Optional[str] = None
    hint: Optional[str] = None
    remaining_attempts: Optional[int] = None
    levels_passed: int
    status: str  # "playing", "idle", "none"
    mode: Optional[str] = "progression"  # "progression" or "practice"

class WordleGuessResponse(BaseModel):
    feedback: List[str]
    next_hint: Optional[str]
    revealed_pattern: str
    remaining_attempts: int
    status: str # "playing", "won", "lost", "game_over" -- status of CURRENT WORD or overall game if over
    message: str
    current_round: int
    level: int # Alias for current_round
    total_rounds: int
    levels_passed: int
    current_word_length: Optional[int] = None # Added for UI updates
    word_revealed: Optional[str] = None # Show word if lost or won
    mode: Optional[str] = "progression"  # "progression" or "practice"

class WordleLevelInfo(BaseModel):
    level: int
    status: str  # "locked", "unlocked", "completed"
    playable: bool

class WordleLevelsResponse(BaseModel):
    student_id: str
    class_range: str
    highest_level_reached: int
    total_levels: int
    levels: List[WordleLevelInfo]
