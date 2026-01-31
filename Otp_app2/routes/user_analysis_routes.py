"""
User/Student Analytics Routes - Mobile Optimized
Provides analytics endpoints for students (mobile app consumption)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import statistics

from utils.user_auth import get_current_user
from services.analysis_service import AnalysisService
from models.analysis_models import (
    PeriodType, MetricType,
    StudentDashboard, ProgressData, StrengthsWeaknessesResponse,
    QuizPerformanceResponse, ExamPerformanceResponse,
    ScoreCard, StreakInfo, TodaySummary, Achievement, Recommendation,
    DataPoint, TrendAnalysis, Milestone, CategoryPerformance,
    DomainStats, DifficultyAnalysis, QuizAttempt, ExamAttempt,
    IntelligenceProfile, FeatureUsage, PeerComparison
)
from core.database import db

router = APIRouter(tags=["Analytics Module - Student"])


# ==================== STUDENT DASHBOARD (HOME SCREEN) ====================

@router.get("/analytics/dashboard")
async def get_student_dashboard(
    student_id: Optional[str] = Query(None, description="Optional: Target student ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    📱 Mobile-optimized dashboard endpoint
    GET /user/analytics/dashboard
    
    Returns quick performance snapshot, streak info, today's activity,
    achievements, and personalized recommendations.
    
    Perfect for the home screen of the mobile app.
    """
    try:
        # Use provided student_id or default to current user
        target_id = student_id if student_id else str(current_user["_id"])
        
        # Get student details
        student = await db.students.find_one({"_id": ObjectId(target_id)})
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        
        # Get overall score
        overall_score = await AnalysisService.get_student_overall_score(target_id, PeriodType.MONTH)
        
        # Get streak information
        streak = await AnalysisService.get_student_streak(target_id)
        
        # Get today's summary
        today_summary = await AnalysisService.get_today_summary(target_id)
        
        # Get recent achievements (mock for now - can be enhanced later)
        recent_achievements = []
        # TODO: Implement achievements system
        
        # Get personalized recommendation
        recommendation = await AnalysisService.get_student_recommendation(target_id)
        
        return {
            "success": True,
            "student_id": target_id,
            "student_name": student.get("student_name", "Student"),
            "class": student.get("class", "N/A"),
            "dashboard": {
                "overall_score": overall_score.dict(),
                "streak": streak.dict(),
                "today_summary": today_summary.dict(),
                "recent_achievements": recent_achievements,
                "next_recommendation": recommendation.dict() if recommendation else None
            },
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard: {str(e)}")


# ==================== PROGRESS TRACKING ====================

@router.get("/analytics/progress")
async def get_student_progress(
    period: PeriodType = Query(PeriodType.MONTH, description="Time period: week, month, 3months, year, all"),
    metric: MetricType = Query(MetricType.OVERALL, description="Metric type: overall, quiz, exam"),
    student_id: Optional[str] = Query(None, description="Optional: Target student ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    📈 Progress tracking over time
    GET /user/analytics/progress
    
    Returns time-series data showing performance trends, suitable for line/area charts.
    Shows improvement over time with trend analysis and milestones.
    """
    try:
        student_id = str(current_user["_id"])
        start_date, end_date = AnalysisService.get_date_range(period)
        
        # Calculate interval based on period
        if period == PeriodType.WEEK:
            interval_days = 1  # Daily data points
        elif period == PeriodType.MONTH:
            interval_days = 7  # Weekly data points
        else:
            interval_days = 30  # Monthly data points
        
        # Generate data points
        data_points = []
        current_date = start_date
        
        while current_date <= end_date:
            next_date = current_date + timedelta(days=interval_days)
            
            # Get quiz scores in this interval
            quiz_scores = []
            quiz_submissions = await db.quiz_submissions.find({
                "student_id": ObjectId(target_id),
                "submitted_at": {"$gte": current_date, "$lt": next_date}
            }).to_list(length=None)
            
            quiz_scores = [sub["score"] for sub in quiz_submissions if "score" in sub]
            
            # Get exam scores in this interval
            exam_scores = []
            exam_evaluations = await db.exam_evaluations.find({
                "student_id": ObjectId(target_id),
                "created_at": {"$gte": current_date, "$lt": next_date}
            }).to_list(length=None)
            
            for eva in exam_evaluations:
                if "total_score" in eva and "total_marks" in eva and eva["total_marks"] > 0:
                    percentage = (eva["total_score"] / eva["total_marks"]) * 100
                    exam_scores.append(percentage)
            
            # Calculate average for this period
            if metric == MetricType.QUIZ:
                scores = quiz_scores
            elif metric == MetricType.EXAM:
                scores = exam_scores
            else:  # OVERALL
                scores = quiz_scores + exam_scores
            
            if scores:
                avg_score = statistics.mean(scores)
                data_points.append(DataPoint(
                    date=current_date.strftime("%Y-%m-%d"),
                    score=round(avg_score, 1),
                    quizzes_taken=len(quiz_scores),
                    exams_taken=len(exam_scores)
                ))
            
            current_date = next_date
        
        # Calculate trend
        if len(data_points) >= 2:
            first_score = data_points[0].score
            last_score = data_points[-1].score
            change = last_score - first_score
            percentage_change = (change / first_score * 100) if first_score > 0 else 0
            
            if percentage_change > 10:
                trend_direction = "improving"
                trend_rate = "rapid" if percentage_change > 20 else "moderate"
                message = f"Great job! Your scores are improving rapidly. (+{percentage_change:.1f}%)"
            elif percentage_change > 0:
                trend_direction = "improving"
                trend_rate = "slow"
                message = f"Good progress! Keep it up. (+{percentage_change:.1f}%)"
            elif percentage_change < -10:
                trend_direction = "declining"
                trend_rate = "concerning"
                message = f"We notice a decline. Let's work on improvement. ({percentage_change:.1f}%)"
            else:
                trend_direction = "stable"
                trend_rate = "steady"
                message = "Consistent performance. Push harder for improvement!"
            
            trend_analysis = TrendAnalysis(
                direction=trend_direction,
                rate=trend_rate,
                message=message,
                percentage_change=f"+{percentage_change:.1f}%" if percentage_change >= 0 else f"{percentage_change:.1f}%"
            )
        else:
            trend_analysis = TrendAnalysis(
                direction="stable",
                rate="insufficient_data",
                message="Not enough data yet. Take more quizzes and exams to see your progress!",
                percentage_change=None
            )
        
        # Find milestones
        milestones = []
        for dp in data_points:
            if dp.score >= 75 and not any(m.title == "Crossed 75% mark" for m in milestones):
                milestones.append(Milestone(
                    title="Crossed 75% mark",
                    achieved_on=dp.date,
                    icon="star"
                ))
            if dp.score >= 90 and not any(m.title == "Achieved 90+!" for m in milestones):
                milestones.append(Milestone(
                    title="Achieved 90+!",
                    achieved_on=dp.date,
                    icon="trophy"
                ))
        
        return {
            "success": True,
            "student_id": target_id,
            "period": period,
            "metric": metric,
            "progress_data": {
                "chart_type": "line",
                "data_points": [dp.dict() for dp in data_points],
                "trend_analysis": trend_analysis.dict(),
                "milestones_achieved": [m.dict() for m in milestones]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching progress: {str(e)}")


# ==================== STRENGTHS & WEAKNESSES ====================

@router.get("/analytics/strengths-weaknesses")
async def get_strengths_weaknesses(
    student_id: Optional[str] = Query(None, description="Optional: Target student ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    🎯 Strengths and weaknesses analysis
    GET /user/analytics/strengths-weaknesses
    
    Shows top performing domains/subjects and areas needing improvement.
    Includes career intelligence profile if available.
    """
    try:
        target_id = student_id if student_id else str(current_user["_id"])
        
        # Get domain-wise quiz performance
        pipeline = [
            {"$match": {"student_id": ObjectId(target_id)}},
            {"$group": {
                "_id": "$domain",
                "scores": {"$push": "$score"},
                "attempts": {"$sum": 1}
            }},
            {"$project": {
                "domain": "$_id",
                "avg_score": {"$avg": "$scores"},
                "total_attempts": "$attempts"
            }},
            {"$sort": {"avg_score": -1}}
        ]
        
        domain_results = await db.quiz_submissions.aggregate(pipeline).to_list(length=None)
        
        strengths = []
        weaknesses = []
        balanced = []
        
        color_map = {
            0: "#4CAF50",  # Green for top
            1: "#8BC34A",  # Light green
            2: "#CDDC39",  # Yellow-green
        }
        
        for idx, result in enumerate(domain_results):
            domain = result.get("domain", "Unknown")
            avg_score = result.get("avg_score", 0)
            attempts = result.get("total_attempts", 0)
            
            if avg_score >= 80:
                strengths.append(CategoryPerformance(
                    category=domain,
                    category_type="domain",
                    score=round(avg_score, 1),
                    total_attempts=attempts,
                    rank=idx + 1,
                    color=color_map.get(len(strengths), "#4CAF50"),
                    icon="star",
                    message=f"Outstanding performance in {domain}!"
                ))
            elif avg_score < 65:
                weaknesses.append(CategoryPerformance(
                    category=domain,
                    category_type="domain",
                    score=round(avg_score, 1),
                    total_attempts=attempts,
                    rank=-(len(weaknesses) + 1),
                    color="#FF9800" if avg_score >= 50 else "#F44336",
                    icon="trending_down",
                    message=f"Needs focus - {domain} requires more practice",
                    recommendation=f"Take 3 more {domain} quizzes this week"
                ))
            else:
                balanced.append({
                    "category": domain,
                    "score": round(avg_score, 1),
                    "message": "Steady performance"
                })
        
        # Get intelligence profile from career analysis
        intelligence_profile = None
        career_doc = await db.career_analysis.find_one(
            {"student_id": ObjectId(target_id)},
            sort=[("created_at", -1)]
        )
        
        if career_doc and "normalized_percentages" in career_doc:
            # Find top intelligence
            percentages = career_doc["normalized_percentages"]
            top_intel = max(percentages, key=percentages.get)
            top_score = percentages[top_intel]
            
            career_suggestions = career_doc.get("career_suggestions", [])
            
            intelligence_profile = IntelligenceProfile(
                top_intelligence=top_intel.replace("_", "-").title(),
                score=round(top_score, 1),
                description=f"You excel in {top_intel.replace('_', ' ')} thinking",
                recommended_careers=career_suggestions[:3] if career_suggestions else []
            )
        
        return {
            "success": True,
            "student_id": target_id,
            "analysis_date": datetime.now(timezone.utc).isoformat(),
            "strengthweaknesses": {
                "strengths": [s.dict() for s in strengths],
                "weaknesses": [w.dict() for w in weaknesses],
                "intelligence_profile": intelligence_profile.dict() if intelligence_profile else None,
                "balanced_areas": balanced
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching strengths/weaknesses: {str(e)}")


# ==================== ACHIEVEMENTS & BADGES ====================

@router.get("/analytics/achievements")
async def get_achievements(
    student_id: Optional[str] = Query(None, description="Optional: Target student ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    🏆 Achievements and badges
    GET /user/analytics/achievements
    
    Shows earned badges, progress toward new achievements,
    streaks, and leaderboard position.
    """
    try:
        target_id = student_id if student_id else str(current_user["_id"])
        student = await db.students.find_one({"_id": ObjectId(target_id)})
        
        # Get quiz and exam counts
        total_quizzes = await db.quiz_submissions.count_documents({"student_id": ObjectId(target_id)})
        total_exams = await db.exam_evaluations.count_documents({"student_id": ObjectId(target_id)})
        
        # Calculate level based on activity
        total_points = (total_quizzes * 10) + (total_exams * 50)
        current_level = min(total_points // 500, 10)  # Max level 10
        
        level_names = ["Beginner", "Learner", "Student", "Scholar", "Expert Scholar", 
                      "Master", "Grand Master", "Legend", "Champion", "Genius"]
        
        # Earned badges (simplified - can be enhanced with actual badge system)
        recent_badges = []
        in_progress = []
        
        if total_quizzes >= 10:
            recent_badges.append({
                "id": "badge_quiz_10",
                "name": "Quiz Starter",
                "icon_url": "/badges/quiz_starter.png",
                "description": "Completed 10 quizzes",
                "earned_at": datetime.now(timezone.utc).isoformat(),
                "rarity": "common",
                "points": 50
            })
        
        if total_quizzes >= 50:
            recent_badges.append({
                "id": "badge_quiz_50",
                "name": "Quiz Master",
                "icon_url": "/badges/quiz_master.png",
                "description": "Completed 50 quizzes",
                "earned_at": datetime.now(timezone.utc).isoformat(),
                "rarity": "rare",
                "points": 100
            })
        elif total_quizzes >= 10:
            in_progress.append({
                "id": "badge_quiz_50",
                "name": "Quiz Master",
                "description": "Complete 50 quizzes",
                "icon_url": "/badges/quiz_master_locked.png",
                "current_progress": total_quizzes,
                "target": 50,
                "progress_percentage": (total_quizzes / 50) * 100,
                "estimated_completion": f"{50 - total_quizzes} more quizzes to go!"
            })
        
        # Streak info
        streak = await AnalysisService.get_student_streak(target_id)
        
        # Leaderboard position (simplified)
        all_students_class = await db.students.count_documents({"class": student.get("class", "")})
        
        return {
            "success": True,
            "student_id": target_id,
            "total_achievements": len(recent_badges),
            "total_points": total_points,
            "level": {
                "current": current_level,
                "name": level_names[current_level] if current_level < len(level_names) else "Genius",
                "next_level": level_names[current_level + 1] if current_level + 1 < len(level_names) else "Max Level",
                "points_to_next": 500 - (total_points % 500),
                "progress_percentage": round((total_points % 500) / 500 * 100, 1)
            },
            "recent_badges": recent_badges,
            "in_progress": in_progress,
            "streaks": streak.dict(),
            "leaderboard_position": {
                "overall_rank": None,  # TODO: Calculate actual rank
                "class_rank": None,
                "total_students": all_students_class,
                "percentile": None,
                "message": "Rank calculation coming soon!"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching achievements: {str(e)}")


# ==================== QUIZ PERFORMANCE (DETAILED) ====================

@router.get("/analytics/quiz-performance")
async def get_quiz_performance(
    domain: Optional[str] = Query(None, description="Filter by domain"),
    period: PeriodType = Query(PeriodType.MONTH, description="Time period"),
    student_id: Optional[str] = Query(None, description="Optional: Target student ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    📊 Detailed quiz performance analytics
    GET /user/analytics/quiz-performance
    
    Shows domain breakdown, difficulty analysis, and recent quiz attempts.
    """
    try:
        target_id = student_id if student_id else str(current_user["_id"])
        start_date, end_date = AnalysisService.get_date_range(period)
        
        # Build query
        match_query = {
            "student_id": ObjectId(target_id),
            "submitted_at": {"$gte": start_date, "$lte": end_date}
        }
        if domain:
            match_query["domain"] = domain
        
        # Get quiz submissions
        submissions = await db.quiz_submissions.find(match_query).sort("submitted_at", -1).to_list(length=None)
        
        if not submissions:
            return {
                "success": True,
                "message": "No quiz data available for this period",
                "student_id": target_id,
                "period": period,
                "quiz_stats": None
            }
        
        # Calculate statistics
        scores = [sub.get("score", 0) for sub in submissions]
        total_quizzes = len(submissions)
        total_questions = sum([sub.get("total_questions", 0) for sub in submissions])
        avg_score = statistics.mean(scores)
        
        # Domain breakdown
        domain_groups = {}
        for sub in submissions:
            dom = sub.get("domain", "Unknown")
            if dom not in domain_groups:
                domain_groups[dom] = []
            domain_groups[dom].append(sub.get("score", 0))
        
        domain_breakdown = []
        for dom, scores_list in domain_groups.items():
            domain_breakdown.append({
                "domain": dom,
                "quizzes_taken": len(scores_list),
                "average_score": round(statistics.mean(scores_list), 1),
                "accuracy": round(statistics.mean(scores_list), 1),
                "best_score": max(scores_list),
                "worst_score": min(scores_list),
                "trend": "stable",
                "color": "#4CAF50"
            })
        
        # Recent quizzes (last 5)
        recent_quizzes = []
        for sub in submissions[:5]:
            recent_quizzes.append({
                "quiz_id": str(sub.get("_id", "")),
                "domain": sub.get("domain", "Unknown"),
                "score": sub.get("score", 0),
                "total_questions": sub.get("total_questions", 0),
                "correct_answers": sub.get("correct_answers", 0),
                "time_taken": sub.get("time_taken", "N/A"),
                "completed_at": sub.get("submitted_at", datetime.now(timezone.utc)).isoformat()
            })
        
        return {
            "success": True,
            "student_id": target_id,
            "period": period,
            "quiz_stats": {
                "total_quizzes_taken": total_quizzes,
                "total_questions_answered": total_questions,
                "average_score": round(avg_score, 1),
                "accuracy_rate": round(avg_score, 1),
                "average_time_per_quiz": "N/A",  # TODO: Calculate from time_taken
                "improvement": None  # TODO: Calculate improvement percentage
            },
            "domain_breakdown": domain_breakdown,
            "difficulty_analysis": {
                "easy": {"attempted": 0, "correct": 0, "accuracy": 0.0},
                "medium": {"attempted": 0, "correct": 0, "accuracy": 0.0},
                "hard": {"attempted": 0, "correct": 0, "accuracy": 0.0}
            },
            "recent_quizzes": recent_quizzes
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching quiz performance: {str(e)}")


# ==================== EXAM PERFORMANCE (DETAILED) ====================

@router.get("/analytics/exam-performance")
async def get_exam_performance(
    subject: Optional[str] = Query(None, description="Filter by subject"),
    period: PeriodType = Query(PeriodType.MONTH, description="Time period"),
    student_id: Optional[str] = Query(None, description="Optional: Target student ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    📝 Detailed exam performance analytics
    GET /user/analytics/exam-performance
    
    Shows subject breakdown, AI feedback summary, and recent exam attempts.
    """
    try:
        target_id = student_id if student_id else str(current_user["_id"])
        start_date, end_date = AnalysisService.get_date_range(period)
        
        # Get exam evaluations
        evaluations = await db.exam_evaluations.find({
            "student_id": ObjectId(target_id),
            "created_at": {"$gte": start_date, "$lte": end_date}
        }).sort("created_at", -1).to_list(length=None)
        
        if not evaluations:
            return {
                "success": True,
                "message": "No exam data available for this period",
                "student_id": target_id,
                "period": period,
                "exam_stats": None
            }
        
        # Calculate statistics
        scores = []
        for eva in evaluations:
            if "total_score" in eva and "total_marks" in eva and eva["total_marks"] > 0:
                percentage = (eva["total_score"] / eva["total_marks"]) * 100
                scores.append(percentage)
        
        total_exams = len(evaluations)
        avg_score = statistics.mean(scores) if scores else 0
        highest = max(scores) if scores else 0
        lowest = min(scores) if scores else 0
        
        # Recent exams (last 5)
        recent_exams = []
        for eva in evaluations[:5]:
            recent_exams.append({
                "exam_id": str(eva.get("_id", "")),
                "subject": eva.get("paper_id", "Unknown"),  # TODO: Get actual subject
                "score": eva.get("total_score", 0),
                "total_marks": eva.get("total_marks", 0),
                "submitted_at": eva.get("created_at", datetime.now(timezone.utc)).isoformat(),
                "evaluated_at": eva.get("evaluated_at", eva.get("created_at", datetime.now(timezone.utc))).isoformat(),
                "feedback_summary": "Good performance"  # TODO: Extract from evaluations
            })
        
        return {
            "success": True,
            "student_id": target_id,
            "period": period,
            "exam_stats": {
                "total_exams_taken": total_exams,
                "average_score": round(avg_score, 1),
                "highest_score": round(highest, 1),
                "lowest_score": round(lowest, 1),
                "improvement": None  # TODO: Calculate
            },
            "subject_breakdown": [],  # TODO: Group by subject
            "question_type_performance": {},  # TODO: Analyze question types
            "ai_feedback_summary": {
                "common_strengths": ["Clear answers", "Good understanding"],
                "common_weaknesses": ["Need more examples", "Time management"],
                "recommendations": ["Practice descriptive answers", "Review concepts"]
            },
            "recent_exams": recent_exams
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching exam performance: {str(e)}")


# ==================== CAREER PROGRESS ====================

@router.get("/analytics/career-progress")
async def get_career_progress(
    student_id: Optional[str] = Query(None, description="Optional: Target student ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    🎓 Career guidance progress
    GET /user/analytics/career-progress
    
    Shows intelligence assessment results, career recommendations,
    and progress over multiple attempts.
    """
    try:
        target_id = student_id if student_id else str(current_user["_id"])
        
        # Get all career assessments
        assessments = await db.career_analysis.find(
            {"student_id": ObjectId(target_id)}
        ).sort("created_at", -1).to_list(length=None)
        
        if not assessments:
            return {
                "success": True,
                "message": "No career assessments completed yet. Take your first assessment!",
                "student_id": target_id,
                "assessments_completed": 0
            }
        
        latest = assessments[0]
        percentages = latest.get("normalized_percentages", {})
        
        # Get dominant intelligences
        dominant_intelligences = sorted(
            percentages.items(),
            key=lambda x: x[1],
            reverse=True
        )[:2]
        
        # Format for response
        intelligence_list = []
        colors = ["#3F51B5", "#E91E63", "#4CAF50", "#FF9800"]
        for idx, (intel, score) in enumerate(dominant_intelligences):
            intelligence_list.append({
                "type": intel.replace("_", "-").title(),
                "percentage": round(score, 1),
                "description": f"Strong {intel.replace('_', ' ')} abilities",
                "color": colors[idx % len(colors)]
            })
        
        # Chart data for radar chart
        chart_data = {
            "type": "radar",
            "labels": [k.replace("_", " ").title() for k in percentages.keys()],
            "values": [round(v, 1) for v in percentages.values()]
        }
        
        # Career recommendations
        career_suggestions = latest.get("career_suggestions", [])
        recommended_careers = []
        for idx, career in enumerate(career_suggestions[:3]):
            recommended_careers.append({
                "title": career,
                "match_percentage": round(100 - (idx * 5), 1),  # Simplified
                "description": f"Career in {career}",
                "required_skills": ["Skill 1", "Skill 2"],
                "icon": "work",
                "color": "#4CAF50"
            })
        
        return {
            "success": True,
            "student_id": target_id,
            "assessments_completed": len(assessments),
            "latest_assessment": {
                "completed_at": latest.get("created_at", datetime.now(timezone.utc)).isoformat(),
                "attempt_number": latest.get("attempt_number", 1)
            },
            "intelligence_profile": {
                "dominant_intelligences": intelligence_list,
                "chart_data": chart_data
            },
            "recommended_careers": recommended_careers,
            "progress_over_time": [
                {
                    "attempt": idx + 1,
                    "date": asmt.get("created_at", datetime.now(timezone.utc)).strftime("%Y-%m-%d"),
                    "dominant": max(asmt.get("normalized_percentages", {}).items(), key=lambda x: x[1])[0].title() if asmt.get("normalized_percentages") else "N/A",
                    "score": round(max(asmt.get("normalized_percentages", {}).values()) if asmt.get("normalized_percentages") else 0, 1)
                }
                for idx, asmt in enumerate(reversed(assessments))
            ],
            "recommended_actions": [
                {
                    "action": "Explore coding tutorials",
                    "reason": "Matches your logical-mathematical strength",
                    "priority": "high"
                }
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching career progress: {str(e)}")
