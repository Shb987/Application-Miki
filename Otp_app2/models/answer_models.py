from pydantic import BaseModel
from typing import List

class AnswerRequest(BaseModel):
    student_id: str
    category: str
    question_ids: List[str]              # multiple question IDs
    answers: List[int]                   # selected option indexes
    attempt: int = 0            # default attempt = 0
    total_marks: int = 0        # default total marks = 0