from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

# -------------------------------------------------------------
# Competitive Exam Category Models
# -------------------------------------------------------------
class CompetitiveCategoryCreateRequest(BaseModel):
    category_name: str = Field(..., description="Competitive exam category name, e.g. 'Kerala PSC', 'UPSC Civil Services'")
    description: Optional[str] = Field(None, description="Optional description of the category")
    icon: Optional[str] = Field("fa-bookmark", description="FontAwesome icon class, e.g. 'fa-graduation-cap'")
    is_active: bool = Field(True, description="Whether the category is active")

class CompetitiveCategoryResponse(BaseModel):
    status: str = "success"
    message: str
    category: Optional[Dict[str, Any]] = None

# -------------------------------------------------------------
# Competitive Exam Tutorial Models
# -------------------------------------------------------------
class CompetitiveVideoLink(BaseModel):
    title: str
    published_at: Optional[str] = ""
    link: str
    thumbnail: Optional[str] = None
    duration: Optional[str] = None

class CompetitiveTutorialCreateRequest(BaseModel):
    category_name: Optional[str] = Field(None, description="Competitive exam category, e.g. 'Kerala PSC', 'UPSC'")
    exam_name: str = Field(..., description="Exam name, e.g. 'KAS', 'Civil Services', 'SSC CGL'")
    subject: str = Field(..., description="Subject name, e.g. 'General Studies', 'Maths'")
    topic: Optional[str] = Field(None, description="Topic or chapter name")
    title: Optional[str] = Field(None, description="Tutorial Title")
    description: Optional[str] = Field(None, description="Description of the tutorial")
    youtube_url: Optional[str] = Field(None, description="YouTube playlist, channel, or video URL")
    video_links: Optional[List[CompetitiveVideoLink]] = Field(default_factory=list, description="Explicit video items")

class CompetitiveTutorialResponse(BaseModel):
    status: str = "success"
    message: str
    tutorial_id: Optional[str] = None
    count: int = 0

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
