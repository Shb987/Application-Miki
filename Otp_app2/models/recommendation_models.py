from pydantic import BaseModel
from typing import List
class Recommendation(BaseModel):
    student_id: str
    career: str                 # e.g. "Scientist"
    tutorials: List[str]         # list of lecture titles
    videos: List[str]           # list of video URLs