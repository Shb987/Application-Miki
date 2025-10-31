
from pydantic import BaseModel,Field
from typing import Optional,List

class Question(BaseModel):
    category: str
    text: str
    options: Optional[List[str]] = None         # for text-based MCQs
    image_options: Optional[List[str]] = None   # for image-based MCQs
    correct_index: Optional[int] = None         # index of correct answer
    correct_answer: Optional[str] = None        # text of correct answer (for normal MCQs)
    age_min: Optional[int] = None
    age_max: Optional[int] = None
