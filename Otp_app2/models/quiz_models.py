from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

# Enums for better type safety
class QuestionType(str, Enum):
    # Standard Types
    MCQ = "MCQ"
    TRUE_FALSE = "TrueFalse"
    FILL_IN_BLANK = "FillInBlank"
    
    # IQ-Boosting Types
    PATTERN_RECOGNITION = "PatternRecognition"
    LOGICAL_REASONING = "LogicalReasoning"
    ANALOGY = "Analogy"
    PUZZLE = "Puzzle"
    PICTURE_REASONING = "PictureReasoning"
    
    # Grammar Types
    SENTENCE_CORRECTION = "SentenceCorrection"
    ERROR_SPOTTING = "ErrorSpotting"
    VOCABULARY = "Vocabulary"
    SENTENCE_FORMATION = "SentenceFormation"
    PARTS_OF_SPEECH = "PartsOfSpeech"

class DifficultyLevel(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"

class ClassRange(str, Enum):
    PRIMARY_LOWER = "1-3"
    PRIMARY_UPPER = "3-5"
    MIDDLE_SCHOOL = "6-8"
    HIGH_SCHOOL = "9-10"
    HIGHER_SECONDARY = "11-12"

# Quiz Question Model
class QuizQuestion(BaseModel):
    domain: str  # GK, Literature, Sports, Grammar, IQ & Reasoning, etc.
    question_text: str
    question_type: QuestionType
    options: Optional[List[str]] = None  # For MCQ, Analogy, etc.
    image_url: Optional[str] = None  # For picture-based questions
    correct_answer: str
    difficulty_level: DifficultyLevel
    class_range: ClassRange
    marks: int = Field(default=1, ge=1)
    explanation: Optional[str] = None
    hints: Optional[str] = None
    created_by: Optional[str] = None  # Admin ID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = True

# Quiz Submission Model
class QuizSubmission(BaseModel):
    user_id: str
    student_name: Optional[str] = None
    quiz_questions: List[str]  # List of question IDs
    user_answers: Dict[str, str]  # question_id -> user's answer
    score: float
    total_marks: int
    percentage: float
    domain: str
    class_range: str
    submitted_at: datetime

# Request Models
class QuizFilter(BaseModel):
    domain: Optional[str] = None
    class_range: Optional[ClassRange] = None
    difficulty_level: Optional[DifficultyLevel] = None
    limit: int = Field(default=10, ge=1, le=50)

class QuizAnswerSubmission(BaseModel):
    question_id: str
    user_answer: str

class QuizSubmitRequest(BaseModel):
    domain: str
    class_range: str
    answers: List[QuizAnswerSubmission]

# Response Models
class QuizQuestionResponse(BaseModel):
    question_id: str
    domain: str
    question_text: str
    question_type: str
    options: Optional[List[str]] = None
    image_url: Optional[str] = None
    difficulty_level: str
    marks: int
    hints: Optional[str] = None

class QuizResultDetail(BaseModel):
    question_id: str
    question_text: str
    user_answer: str
    correct_answer: str
    is_correct: bool
    marks_awarded: float
    explanation: Optional[str] = None
