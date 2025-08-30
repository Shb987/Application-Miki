
from pydantic import BaseModel,Field
from typing import Optional,List


class Question(BaseModel):
    category: str          # e.g. "verbal-linguistic"
    text: str              # actual question
    options: List[str] = Field(default_factory=list)  # ✅ correct way
    answer: Optional[str] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
