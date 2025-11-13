from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime

class Career_analyzer(BaseModel):
    student_id: str
    attempt: int
    top_category: str
    recommended_career: List[str]
    scores: Dict[str, float]              # category_name → score
    timestamp_utc: datetime
