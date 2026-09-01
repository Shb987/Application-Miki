from pydantic import BaseModel, Field
from typing import List, Optional, Any
from enum import Enum

class MathOperationEnum(str, Enum):
    ADDITION = "addition"
    SUBTRACTION = "subtraction"
    MULTIPLICATION = "multiplication"
    DIVISION = "division"

class GameModeEnum(str, Enum):
    SOLO = "solo"
    MULTIPLAYER = "multiplayer"

class QuestionPublic(BaseModel):
    id: str
    expression: str
    operation: MathOperationEnum
    options: List[float]

class StartGameRequest(BaseModel):
    mode: GameModeEnum = Field(default=GameModeEnum.SOLO, description="Game mode: 'solo' or 'multiplayer'")
    grade: int = Field(default=5, ge=1, le=12, description="Student class/grade from 1 to 12")
    operations: Optional[List[MathOperationEnum]] = Field(
        default=None, 
        description="Operations list. Defaults to all 4 operations if empty."
    )
    num_questions: int = Field(default=10, ge=3, le=30, description="Number of questions")
    token: Optional[str] = Field(default=None, description="Provide 6-character token to JOIN an existing multiplayer room")

class StartGameResponse(BaseModel):
    session_id: str
    mode: GameModeEnum
    token: Optional[str] = None
    grade: int
    operations: List[MathOperationEnum]
    status: str
    player1_name: Optional[str] = None
    player2_name: Optional[str] = None
    questions: List[QuestionPublic]

class UserAnswerInput(BaseModel):
    question_id: str
    selected_option: float
    time_spent_seconds: Optional[float] = 0.0

class SubmitGameRequest(BaseModel):
    session_id: str
    answers: List[UserAnswerInput]
    total_time_seconds: Optional[float] = 0.0

class QuestionResultDetail(BaseModel):
    question_id: str
    expression: str
    user_answer: float
    correct_answer: float
    is_correct: bool

class PlayerSummary(BaseModel):
    user_id: Optional[str] = None
    name: Optional[str] = None
    is_submitted: bool = False
    correct_count: int = 0
    total_score: int = 0
    time_taken_seconds: float = 0.0

class SubmitGameResponse(BaseModel):
    session_id: str
    mode: GameModeEnum
    status: str
    token: Optional[str] = None
    total_questions: int = 0
    user_correct_count: int = 0
    user_accuracy_percentage: float = 0.0
    user_total_score: int = 0
    time_taken_seconds: float = 0.0
    winner: Optional[str] = None
    winner_name: Optional[str] = None
    player1: Optional[PlayerSummary] = None
    player2: Optional[PlayerSummary] = None
    details: List[QuestionResultDetail] = []
