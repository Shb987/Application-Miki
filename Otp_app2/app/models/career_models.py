from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime

class CareerAnalyzer(BaseModel):  # Optional: camel case name cleanup
    student_id: str
    attempt: int
    top_category: str
    recommended_career: List[str]      # Stored as array in MongoDB
    scores: Dict[str, float]           # category_name → score
    top_5_careers: List[Dict] = []
    timestamp_utc: datetime


