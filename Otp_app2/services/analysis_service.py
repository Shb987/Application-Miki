"""
Analysis Service - Business Logic for Analytics Module
Handles data aggregation, statistical calculations, and analytics generation
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from bson import ObjectId
from core.database import db
from models.analysis_models import (
    PeriodType, TrendDirection, PerformanceLevel,
    ScoreCard, StreakInfo, TodaySummary, Achievement, Recommendation,
    DataPoint, TrendAnalysis, CategoryPerformance, DomainStats,
    PlatformStatistics, StudentAnalyticsSummary, DomainAnalytics,
    SubjectAnalytics, EngagementMetrics
)
import statistics


class AnalysisService:
    """Service for analytics data aggregation and calculations"""

    @staticmethod
    def get_date_range(period: PeriodType) -> tuple:
        """Get start and end date for a period"""
        now = datetime.now(timezone.utc)
        
        if period == PeriodType.WEEK:
            start_date = now - timedelta(days=7)
        elif period == PeriodType.MONTH:
            start_date = now - timedelta(days=30)
        elif period == PeriodType.THREE_MONTHS:
            start_date = now - timedelta(days=90)
        elif period == PeriodType.YEAR:
            start_date = now - timedelta(days=365)
        else:  # ALL
            start_date = datetime(2000, 1, 1, tzinfo=timezone.utc)
        
        return start_date, now

    @staticmethod
    def calculate_performance_level(score: float) -> tuple:
        """Calculate performance level and color"""
        if score >= 90:
            return PerformanceLevel.EXCELLENT, "#4CAF50"
        elif score >= 75:
            return PerformanceLevel.GOOD, "#2196F3"
        elif score >= 60:
            return PerformanceLevel.AVERAGE, "#FF9800"
        else:
            return PerformanceLevel.NEEDS_IMPROVEMENT, "#F44336"

    @staticmethod
    def calculate_trend(current: float, previous: float) -> TrendDirection:
        """Calculate trend direction"""
        if current > previous * 1.05:  # 5% increase
            return TrendDirection.UP
        elif current < previous * 0.95:  # 5% decrease
            return TrendDirection.DOWN
        else:
            return TrendDirection.STABLE

    @staticmethod
    async def get_student_streak(student_id: str) -> StreakInfo:
        """Calculate student's learning streak"""
        try:
            # Get quiz and exam submissions sorted by date
            quiz_dates = []
            exam_dates = []
            
            # Get quiz submission dates
            quiz_submissions = await db.quiz_submissions.find(
                {"student_id": ObjectId(student_id)},
                {"submitted_at": 1}
            ).sort("submitted_at", -1).to_list(length=None)
            quiz_dates = [sub["submitted_at"].date() for sub in quiz_submissions if "submitted_at" in sub]
            
            # Get exam submission dates
            exam_submissions = await db.exam_evaluations.find(
                {"student_id": ObjectId(student_id)},
                {"created_at": 1}
            ).sort("created_at", -1).to_list(length=None)
            exam_dates = [eva["created_at"].date() for eva in exam_submissions if "created_at" in eva]
            
            # Combine and sort all activity dates
            all_dates = sorted(set(quiz_dates + exam_dates), reverse=True)
            
            if not all_dates:
                return StreakInfo(
                    current_days=0,
                    best_streak=0,
                    status="inactive",
                    message="Start your learning streak today!"
                )
            
            # Calculate current streak
            current_streak = 0
            today = datetime.now(timezone.utc).date()
            check_date = today
            
            for date in all_dates:
                if date == check_date or date == check_date - timedelta(days=1):
                    current_streak += 1
                    check_date = date - timedelta(days=1)
                else:
                    break
            
            # Calculate best streak
            best_streak = 1
            temp_streak = 1
            for i in range(len(all_dates) - 1):
                if (all_dates[i] - all_dates[i + 1]).days == 1:
                    temp_streak += 1
                    best_streak = max(best_streak, temp_streak)
                else:
                    temp_streak = 1
            
            status = "active" if current_streak > 0 else "broken"
            emoji = "🔥" if current_streak > 0 else "💪"
            message = f"{emoji} {current_streak} days streak! Keep going!" if current_streak > 0 else "Start a new streak today!"
            
            return StreakInfo(
                current_days=current_streak,
                best_streak=max(best_streak, current_streak),
                status=status,
                message=message
            )
        except Exception as e:
            print(f"Error calculating streak: {e}")
            return StreakInfo(
                current_days=0,
                best_streak=0,
                status="error",
                message="Unable to calculate streak"
            )

    @staticmethod
    async def get_today_summary(student_id: str) -> TodaySummary:
        """Get today's activity summary"""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            
            # Count quizzes taken today
            quizzes_today = await db.quiz_submissions.count_documents({
                "student_id": ObjectId(student_id),
                "submitted_at": {"$gte": today_start, "$lt": today_end}
            })
            
            # Count exams completed today
            exams_today = await db.exam_evaluations.count_documents({
                "student_id": ObjectId(student_id),
                "created_at": {"$gte": today_start, "$lt": today_end}
            })
            
            # Count chat messages today (if collection exists)
            chat_messages = 0
            try:
                chat_messages = await db.chat_messages.count_documents({
                    "student_id": ObjectId(student_id),
                    "timestamp": {"$gte": today_start, "$lt": today_end}
                })
            except:
                pass  # Collection might not exist
            
            # Estimate study time (rough calculation)
            study_time = (quizzes_today * 5) + (exams_today * 20)  # 5 min per quiz, 20 min per exam
            
            return TodaySummary(
                quizzes_taken=quizzes_today,
                exams_completed=exams_today,
                study_time_minutes=study_time,
                chat_messages=chat_messages
            )
        except Exception as e:
            print(f"Error getting today summary: {e}")
            return TodaySummary(
                quizzes_taken=0,
                exams_completed=0,
                study_time_minutes=0,
                chat_messages=0
            )

    @staticmethod
    async def get_student_overall_score(student_id: str, period: PeriodType) -> ScoreCard:
        """Calculate student's overall score"""
        try:
            start_date, end_date = AnalysisService.get_date_range(period)
            
            # Get quiz scores
            quiz_scores = []
            quiz_submissions = await db.quiz_submissions.find({
                "student_id": ObjectId(student_id),
                "submitted_at": {"$gte": start_date, "$lte": end_date}
            }).to_list(length=None)
            
            for sub in quiz_submissions:
                if "score" in sub:
                    quiz_scores.append(float(sub["score"]))
            
            # Get exam scores
            exam_scores = []
            exam_evaluations = await db.exam_evaluations.find({
                "student_id": ObjectId(student_id),
                "created_at": {"$gte": start_date, "$lte": end_date}
            }).to_list(length=None)
            
            for eva in exam_evaluations:
                if "total_score" in eva and "total_marks" in eva and eva["total_marks"] > 0:
                    percentage = (eva["total_score"] / eva["total_marks"]) * 100
                    exam_scores.append(percentage)
            
            # Combine scores
            all_scores = quiz_scores + exam_scores
            
            if not all_scores:
                return ScoreCard(
                    current=0.0,
                    previous=None,
                    change=None,
                    trend=None,
                    level=PerformanceLevel.NEEDS_IMPROVEMENT,
                    color="#9E9E9E"
                )
            
            current_score = statistics.mean(all_scores)
            
            # Get previous period score for comparison
            prev_period_start = start_date - (end_date - start_date)
            prev_quiz = await db.quiz_submissions.find({
                "student_id": ObjectId(student_id),
                "submitted_at": {"$gte": prev_period_start, "$lt": start_date}
            }).to_list(length=None)
            
            prev_exam = await db.exam_evaluations.find({
                "student_id": ObjectId(student_id),
                "created_at": {"$gte": prev_period_start, "$lt": start_date}
            }).to_list(length=None)
            
            prev_scores = []
            for sub in prev_quiz:
                if "score" in sub:
                    prev_scores.append(float(sub["score"]))
            for eva in prev_exam:
                if "total_score" in eva and "total_marks" in eva and eva["total_marks"] > 0:
                    percentage = (eva["total_score"] / eva["total_marks"]) * 100
                    prev_scores.append(percentage)
            
            previous_score = statistics.mean(prev_scores) if prev_scores else current_score
            change = current_score - previous_score
            change_str = f"+{change:.1f}" if change >= 0 else f"{change:.1f}"
            trend = AnalysisService.calculate_trend(current_score, previous_score)
            level, color = AnalysisService.calculate_performance_level(current_score)
            
            return ScoreCard(
                current=round(current_score, 1),
                previous=round(previous_score, 1) if prev_scores else None,
                change=change_str,
                trend=trend,
                level=level,
                color=color
            )
        except Exception as e:
            print(f"Error calculating overall score: {e}")
            return ScoreCard(
                current=0.0,
                previous=None,
                change=None,
                trend=None,
                level=PerformanceLevel.NEEDS_IMPROVEMENT,
                color="#9E9E9E"
            )

    @staticmethod
    async def get_student_recommendation(student_id: str) -> Optional[Recommendation]:
        """Get personalized study recommendation"""
        try:
            # Check what student hasn't done recently
            last_week = datetime.now(timezone.utc) - timedelta(days=7)
            
            # Check quiz domains not attempted recently
            recent_quiz_domains = await db.quiz_submissions.find({
                "student_id": ObjectId(student_id),
                "submitted_at": {"$gte": last_week}
            }).to_list(length=None)
            
            attempted_domains = set([sub.get("domain") for sub in recent_quiz_domains if sub.get("domain")])
            
            # Get all available domains
            all_domains = await db.quiz_questions.distinct("domain")
            
            # Find domains not attempted
            not_attempted = [d for d in all_domains if d not in attempted_domains]
            
            if not_attempted:
                domain = not_attempted[0]
                return Recommendation(
                    type="quiz",
                    title=f"Try {domain} Quiz!",
                    description=f"You haven't attempted {domain} in a while",
                    action_url=f"/quiz/{domain}",
                    priority="medium"
                )
            
            # If all domains attempted, recommend exam
            recent_exams = await db.exam_evaluations.count_documents({
                "student_id": ObjectId(student_id),
                "created_at": {"$gte": last_week}
            })
            
            if recent_exams == 0:
                return Recommendation(
                    type="exam",
                    title="Take an Exam!",
                    description="Practice makes perfect - try an exam today",
                    action_url="/exams",
                    priority="high"
                )
            
            return Recommendation(
                type="general",
                title="Keep Learning!",
                description="You're doing great! Continue your learning streak",
                priority="low"
            )
        except Exception as e:
            print(f"Error generating recommendation: {e}")
            return None

    # ==================== ADMIN ANALYTICS ====================

    @staticmethod
    async def get_platform_statistics() -> PlatformStatistics:
        """Get platform-wide statistics"""
        try:
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = now - timedelta(days=7)
            month_start = now - timedelta(days=30)
            
            # Count students
            total_students = await db.students.count_documents({})
            
            # Count parents (users)
            total_parents = await db.users.count_documents({})
            
            # Active users today (based on login_logs or activity)
            active_today = await db.login_logs.distinct("mobile_number", {
                "created_at": {"$gte": today_start}
            })
            
            active_week = await db.login_logs.distinct("mobile_number", {
                "created_at": {"$gte": week_start}
            })
            
            active_month = await db.login_logs.distinct("mobile_number", {
                "created_at": {"$gte": month_start}
            })
            
            # Quiz and exam counts
            total_quizzes = await db.quiz_submissions.count_documents({})
            total_exams = await db.exam_evaluations.count_documents({})
            
            # Chat messages
            total_chats = 0
            try:
                total_chats = await db.chat_messages.count_documents({})
            except:
                pass
            
            # Engagement time (rough estimate)
            avg_engagement = (total_quizzes * 5 + total_exams * 20) / max(total_students, 1)
            
            # New registrations
            new_week = await db.students.count_documents({
                "created_at": {"$gte": week_start}
            })
            
            new_month = await db.students.count_documents({
                "created_at": {"$gte": month_start}
            })
            
            return PlatformStatistics(
                total_students=total_students,
                total_parents=total_parents,
                active_users_today=len(active_today),
                active_users_week=len(active_week),
                active_users_month=len(active_month),
                total_quizzes_taken=total_quizzes,
                total_exams_evaluated=total_exams,
                total_chat_messages=total_chats,
                average_engagement_time_minutes=round(avg_engagement, 1),
                new_registrations_this_week=new_week,
                new_registrations_this_month=new_month
            )
        except Exception as e:
            print(f"Error getting platform statistics: {e}")
            # Return default values
            return PlatformStatistics(
                total_students=0,
                total_parents=0,
                active_users_today=0,
                active_users_week=0,
                active_users_month=0,
                total_quizzes_taken=0,
                total_exams_evaluated=0,
                total_chat_messages=0,
                average_engagement_time_minutes=0.0,
                new_registrations_this_week=0,
                new_registrations_this_month=0
            )

    @staticmethod
    async def get_top_performers(limit: int = 10) -> List[StudentAnalyticsSummary]:
        """Get top performing students"""
        try:
            # Aggregate quiz and exam scores for all students
            pipeline = [
                {
                    "$group": {
                        "_id": "$student_id",
                        "quiz_scores": {"$push": "$score"},
                        "count": {"$sum": 1}
                    }
                },
                {
                    "$project": {
                        "student_id": "$_id",
                        "avg_score": {"$avg": "$quiz_scores"},
                        "total_quizzes": "$count"
                    }
                },
                {"$sort": {"avg_score": -1}},
                {"$limit": limit}
            ]
            
            top_students = await db.quiz_submissions.aggregate(pipeline).to_list(length=None)
            
            result = []
            for student in top_students:
                student_id = student["student_id"]
                student_doc = await db.students.find_one({"_id": ObjectId(student_id)})
                
                if student_doc:
                    result.append(StudentAnalyticsSummary(
                        student_id=str(student_id),
                        student_name=student_doc.get("student_name", "Unknown"),
                        class_name=student_doc.get("class", "N/A"),
                        overall_performance=round(student.get("avg_score", 0), 1),
                        quiz_average=round(student.get("avg_score", 0), 1),
                        exam_average=0.0,  # TODO: Add exam average
                        total_quizzes=student.get("total_quizzes", 0),
                        total_exams=0,
                        last_activity=None,
                        engagement_score=0.0,
                        rank_in_class=None
                    ))
            
            return result
        except Exception as e:
            print(f"Error getting top performers: {e}")
            return []

    @staticmethod
    async def get_domain_analytics() -> List[DomainAnalytics]:
        """Get domain-wise analytics"""
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": "$domain",
                        "total_attempts": {"$sum": 1},
                        "scores": {"$push": "$score"},
                        "students": {"$addToSet": "$student_id"}
                    }
                },
                {
                    "$project": {
                        "domain": "$_id",
                        "total_attempts": 1,
                        "average_score": {"$avg": "$scores"},
                        "total_students": {"$size": "$students"}
                    }
                }
            ]
            
            results = await db.quiz_submissions.aggregate(pipeline).to_list(length=None)
            
            domain_list = []
            for result in results:
                domain_list.append(DomainAnalytics(
                    domain=result.get("domain", "Unknown"),
                    total_attempts=result.get("total_attempts", 0),
                    average_score=round(result.get("average_score", 0), 1),
                    total_students_attempted=result.get("total_students", 0),
                    difficulty_distribution={},
                    top_performers=[]
                ))
            
            return domain_list
        except Exception as e:
            print(f"Error getting domain analytics: {e}")
            return []
