from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ==================== ENUMS ====================

class PeriodType(str, Enum):
    """Time period for analytics"""
    WEEK = "week"
    MONTH = "month"
    THREE_MONTHS = "3months"
    YEAR = "year"
    ALL = "all"


class MetricType(str, Enum):
    """Type of metric to analyze"""
    OVERALL = "overall"
    QUIZ = "quiz"
    EXAM = "exam"
    DOMAIN = "domain"


class TrendDirection(str, Enum):
    """Trend direction"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    IMPROVING = "improving"
    DECLINING = "declining"


class PerformanceLevel(str, Enum):
    """Performance level classification"""
    EXCELLENT = "Excellent"
    GOOD = "Good"
    AVERAGE = "Average"
    NEEDS_IMPROVEMENT = "Needs Improvement"


# ==================== FILTER MODELS ====================

class AnalyticsFilter(BaseModel):
    """Filter for analytics queries"""
    period: Optional[PeriodType] = Field(default=PeriodType.MONTH, description="Time period")
    metric: Optional[MetricType] = Field(default=MetricType.OVERALL, description="Metric type")
    domain: Optional[str] = Field(default=None, description="Filter by domain (for quiz)")
    subject: Optional[str] = Field(default=None, description="Filter by subject (for exam)")
    class_range: Optional[str] = Field(default=None, description="Filter by class")
    start_date: Optional[datetime] = Field(default=None, description="Start date")
    end_date: Optional[datetime] = Field(default=None, description="End date")


# ==================== RESPONSE MODELS ====================

class ScoreCard(BaseModel):
    """Score card for dashboard"""
    current: float
    previous: Optional[float] = None
    change: Optional[str] = None
    trend: Optional[TrendDirection] = None
    level: Optional[PerformanceLevel] = None
    color: Optional[str] = None


class StreakInfo(BaseModel):
    """Streak information"""
    current_days: int
    best_streak: int
    status: str  # "active" or "broken"
    message: str


class TodaySummary(BaseModel):
    """Today's activity summary"""
    quizzes_taken: int = 0
    exams_completed: int = 0
    study_time_minutes: int = 0
    chat_messages: int = 0


class Achievement(BaseModel):
    """Achievement badge"""
    id: str
    title: str
    description: str
    icon: str
    color: str
    earned_at: datetime


class Recommendation(BaseModel):
    """Study recommendation"""
    type: str  # "quiz", "exam", "tutorial", "practice"
    title: str
    description: str
    action_url: Optional[str] = None
    priority: Optional[str] = "medium"  # "high", "medium", "low"


class DataPoint(BaseModel):
    """Single data point for charts"""
    date: str
    score: float
    quizzes_taken: Optional[int] = 0
    exams_taken: Optional[int] = 0


class TrendAnalysis(BaseModel):
    """Trend analysis"""
    direction: TrendDirection
    rate: Optional[str] = None  # "rapid", "moderate", "slow"
    message: str
    percentage_change: Optional[str] = None


class Milestone(BaseModel):
    """Milestone achievement"""
    title: str
    achieved_on: str
    icon: str


class CategoryPerformance(BaseModel):
    """Performance in a category (domain/subject)"""
    category: str
    category_type: str  # "domain", "subject", "question_type"
    score: float
    total_attempts: int
    rank: Optional[int] = None
    color: str
    icon: str
    message: str
    recommendation: Optional[str] = None


class IntelligenceProfile(BaseModel):
    """Intelligence profile from career assessment"""
    top_intelligence: str
    score: float
    description: str
    recommended_careers: List[str]


class DomainStats(BaseModel):
    """Domain-wise statistics"""
    domain: str
    quizzes_taken: int
    average_score: float
    accuracy: float
    best_score: float
    worst_score: float
    trend: TrendDirection
    color: str


class DifficultyAnalysis(BaseModel):
    """Difficulty-wise analysis"""
    attempted: int
    correct: int
    accuracy: float


class QuizAttempt(BaseModel):
    """Recent quiz attempt"""
    quiz_id: str
    domain: str
    score: float
    total_questions: int
    correct_answers: int
    time_taken: str
    completed_at: datetime


class ExamAttempt(BaseModel):
    """Recent exam attempt"""
    exam_id: str
    subject: str
    score: float
    total_marks: float
    submitted_at: datetime
    evaluated_at: Optional[datetime]
    feedback_summary: Optional[str]


class FeatureUsage(BaseModel):
    """Feature usage statistics"""
    sessions: int
    time_spent_minutes: int
    percentage: float


class PeerComparison(BaseModel):
    """Peer comparison data"""
    your_average: float
    class_average: float
    difference: str
    percentile: int
    message: str
    rank_in_class: int
    total_students: int


# ==================== MAIN RESPONSE MODELS ====================

class StudentDashboard(BaseModel):
    """Student analytics dashboard"""
    student_id: str
    student_name: str
    class_name: str
    overall_score: ScoreCard
    streak: StreakInfo
    today_summary: TodaySummary
    recent_achievements: List[Achievement] = []
    next_recommendation: Optional[Recommendation] = None
    last_updated: datetime


class ProgressData(BaseModel):
    """Progress tracking data"""
    student_id: str
    period: PeriodType
    metric: MetricType
    chart_type: str  # "line", "bar", "area"
    data_points: List[DataPoint]
    trend_analysis: TrendAnalysis
    milestones_achieved: List[Milestone] = []


class StrengthsWeaknessesResponse(BaseModel):
    """Strengths and weaknesses analysis"""
    student_id: str
    analysis_date: datetime
    strengths: List[CategoryPerformance]
    weaknesses: List[CategoryPerformance]
    intelligence_profile: Optional[IntelligenceProfile] = None
    balanced_areas: List[Dict[str, Any]] = []


class QuizPerformanceResponse(BaseModel):
    """Quiz performance analytics"""
    student_id: str
    period: PeriodType
    total_quizzes_taken: int
    total_questions_answered: int
    average_score: float
    accuracy_rate: float
    average_time_per_quiz: str
    improvement: Optional[str] = None
    domain_breakdown: List[DomainStats]
    difficulty_analysis: Dict[str, DifficultyAnalysis]
    recent_quizzes: List[QuizAttempt] = []


class ExamPerformanceResponse(BaseModel):
    """Exam performance analytics"""
    student_id: str
    period: PeriodType
    total_exams_taken: int
    average_score: float
    highest_score: float
    lowest_score: float
    improvement: Optional[str] = None
    subject_breakdown: List[Dict[str, Any]]
    question_type_performance: Dict[str, Dict[str, Any]]
    ai_feedback_summary: Dict[str, List[str]]
    recent_exams: List[ExamAttempt] = []


# ==================== ADMIN MODELS ====================

class PlatformStatistics(BaseModel):
    """Platform-wide statistics for admin"""
    total_students: int
    total_parents: int
    active_users_today: int
    active_users_week: int
    active_users_month: int
    total_quizzes_taken: int
    total_exams_evaluated: int
    total_chat_messages: int
    average_engagement_time_minutes: float
    new_registrations_this_week: int
    new_registrations_this_month: int


class StudentAnalyticsSummary(BaseModel):
    """Summary analytics for a student (admin view)"""
    student_id: str
    student_name: str
    class_name: str
    overall_performance: float
    quiz_average: float
    exam_average: float
    total_quizzes: int
    total_exams: int
    last_activity: Optional[datetime]
    engagement_score: float
    rank_in_class: Optional[int]
    areas_of_concern: List[str] = []


class DomainAnalytics(BaseModel):
    """Domain-wise analytics (admin)"""
    domain: str
    total_attempts: int
    average_score: float
    total_students_attempted: int
    difficulty_distribution: Dict[str, int]
    top_performers: List[Dict[str, Any]] = []


class SubjectAnalytics(BaseModel):
    """Subject-wise analytics (admin)"""
    subject: str
    total_exams: int
    average_score: float
    total_students: int
    score_distribution: Dict[str, int]  # ranges like "0-50", "51-75", "76-100"


class EngagementMetrics(BaseModel):
    """Engagement metrics (admin)"""
    feature: str
    total_sessions: int
    total_time_minutes: int
    unique_users: int
    average_session_duration: float
    trend: TrendDirection


class AdminDashboardResponse(BaseModel):
    """Admin analytics dashboard"""
    platform_stats: PlatformStatistics
    top_performers: List[StudentAnalyticsSummary] = []
    bottom_performers: List[StudentAnalyticsSummary] = []
    domain_analytics: List[DomainAnalytics] = []
    subject_analytics: List[SubjectAnalytics] = []
    engagement_metrics: List[EngagementMetrics] = []
    generated_at: datetime
