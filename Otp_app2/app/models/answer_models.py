from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class AnswerDetail(BaseModel):
    question_id: str
    answer_value: int
    correct_index: Optional[int] = None
    mark: Optional[float] = 0
    type: Optional[str] = None


class CategoryAnswers(BaseModel):
    category: str
    total_marks: float = 0
    answers: List[AnswerDetail]


class AttemptData(BaseModel):
    attempt: int = 0
    status: str = "in-progress"          # "in-progress", "completed", "abandoned"
    timestamp_utc: Optional[datetime] = None
    categories: List[CategoryAnswers] = []


class AnswerRequest(BaseModel):
    student_id: str
    category: str                         # Current category being answered
    question_ids: List[str]               # Multiple question IDs
    answers: List[int]                    # Selected answers
    attempt: int = 0                      # Attempt number (default = 0)
