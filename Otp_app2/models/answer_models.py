from pydantic import BaseModel


class AnswerRequest(BaseModel):
    student_id: str
    category: str
    question_id: str
    answer_value: int   # e.g., rating 1–5