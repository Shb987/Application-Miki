from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

# -------------------------------------------------------------
# Submission Request Models
# -------------------------------------------------------------
class ExamAnswerSubmission(BaseModel):
    question_number: int = Field(..., description="1-indexed question number")
    selected_option: Optional[str] = Field(None, description="Selected option: 'A', 'B', 'C', or 'D', or null/empty if skipped")

class ExamSubmitRequest(BaseModel):
    student_id: Optional[str] = Field(None, description="Optional student ID. If omitted, derived from auth token")
    time_taken_seconds: Optional[int] = Field(None, description="Total duration in seconds spent taking the test")
    answers: List[ExamAnswerSubmission] = Field(..., description="Array of student responses")


# -------------------------------------------------------------
# Response & Review Models
# -------------------------------------------------------------
class QuestionReviewItem(BaseModel):
    question_number: int
    question: str
    options: Optional[Dict[str, str]] = None
    selected_option: Optional[str] = None
    correct_answer: Optional[str] = None
    status: str  # "correct", "incorrect", "unattempted"
    marks_awarded: float
    explanation: Optional[str] = None
    chapter_reference: Optional[str] = None

class ExamSubmissionSummary(BaseModel):
    submission_id: str
    paper_id: str
    paper_title: str
    exam_name: str
    subject: str
    total_questions: int
    attempted_count: int
    correct_count: int
    incorrect_count: int
    unattempted_count: int
    total_marks: float
    net_score: float
    positive_marks: float
    negative_marks_deducted: float
    percentage: float
    accuracy: float
    time_taken_seconds: Optional[int] = None
    submitted_at: str

class ExamResultResponse(BaseModel):
    status: str = "success"
    message: str
    summary: ExamSubmissionSummary
    results: List[QuestionReviewItem]

class ExamAttemptItem(BaseModel):
    submission_id: str
    paper_id: str
    paper_title: str
    exam_name: str
    subject: str
    score: float
    total_marks: float
    percentage: float
    accuracy: float
    attempted_count: int
    total_questions: int
    time_taken_seconds: Optional[int] = None
    submitted_at: str

class CompetitiveAnalyticsResponse(BaseModel):
    status: str = "success"
    student_id: str
    student_name: str
    total_tests_taken: int
    average_score: float
    average_percentage: float
    average_accuracy: float
    total_questions_attempted: int
    total_correct: int
    total_incorrect: int
    subject_performance: Dict[str, Any]
    recent_attempts: List[Dict[str, Any]]
