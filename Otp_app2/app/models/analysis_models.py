from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# ==================== CAREER VISUALS ====================

class CareerScoreItem(BaseModel):
    """Linguistic: 85, Logical: 40, etc."""
    label: str
    value: float

class VisualCareerAnalytics(BaseModel):
    """Ready for radar/bar charts"""
    current_top_category: str
    recommended_careers: List[str]
    score_details: List[CareerScoreItem]
    message: str

# ==================== EXAM VISUALS ====================

class ExamHistoryItem(BaseModel):
    """For line charts"""
    date: datetime
    score_percentage: float
    paper_id: str

class VisualExamAnalytics(BaseModel):
    """Historical progression and feedback"""
    overall_avg_score: float
    total_papers_taken: int
    history: List[ExamHistoryItem]
    latest_feedback: str
    trend: str  # "Improving", "Stable", "Declining"

# ==================== QUIZ VISUALS ====================

class DifficultyStats(BaseModel):
    total_taken: int = 0
    avg_percentage: float = 0.0

class QuizHistoryItem(BaseModel):
    """Last 10 results for trend line"""
    date: datetime
    percentage: float

class VisualQuizAnalytics(BaseModel):
    """Difficulty breakdown and trend"""
    domain: str = "Mixed"
    difficulty_breakdown: Dict[str, DifficultyStats]  # {"Easy": ..., "Medium": ..., "Hard": ...}
    last_10_trend: List[QuizHistoryItem]
    overall_accuracy: float

# ==================== MASTER DASHBOARD ====================

class VisualCoreDashboard(BaseModel):
    """The full visual analytics response"""
    student_id: str
    student_name: str
    generated_at: datetime
    career: Optional[VisualCareerAnalytics] = None
    exams: Optional[VisualExamAnalytics] = None
    quizzes: Optional[VisualQuizAnalytics] = None
