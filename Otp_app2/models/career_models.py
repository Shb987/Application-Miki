from pydantic import BaseModel
from typing import List
class Career_analyzer(BaseModel):
    student_id: str
    recommended_career: List[str]                 
    scores: int        
    top_category: str