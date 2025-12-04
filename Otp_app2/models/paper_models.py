from pydantic import BaseModel
from typing import List
class QuestionPaperRequest(BaseModel):
    chapters: List[str]
