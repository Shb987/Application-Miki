"""
Admin Analytics Routes
Provides analytics endpoints for administrators
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timezone
from bson import ObjectId

from utils.admin_auth import get_current_admin
from services.analysis_service import AnalysisService
from models.analysis_models import (
    PeriodType, AnalyticsFilter,
    AdminDashboardResponse, PlatformStatistics,
    StudentAnalyticsSummary, DomainAnalytics,
    SubjectAnalytics, EngagementMetrics
)
from core.database import db

router = APIRouter(tags=["Analytics Module - Admin"])


# ==================== ADMIN ANALYTICS DASHBOARD ====================

@router.get("/analytics/dashboard")
async def get_admin_analytics_dashboard(
    current_admin: dict = Depends(get_current_admin)
):
    """
    Get comprehensive analytics dashboard for administrators.
    Shows platform statistics, top/bottom performers, domain analytics, etc.
    """
    try:
        # Get platform statistics
        platform_stats = await AnalysisService.get_platform_statistics()
        
        # Get top performers
        top_performers = await AnalysisService.get_top_performers(limit=10)
        
        # Get domain analytics
        domain_analytics = await AnalysisService.get_domain_analytics()
        
        return {
            "success": True,
            "data": {
                "platform_stats": platform_stats.dict(),
                "top_performers": [p.dict() for p in top_performers],
                "domain_analytics": [d.dict() for d in domain_analytics],
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching admin dashboard: {str(e)}")


@router.get("/analytics/platform-stats")
async def get_platform_statistics_endpoint(
    current_admin: dict = Depends(get_current_admin)
):
    """
    Get platform-wide statistics.
    Returns total students, active users, quiz/exam counts, etc.
    """
    try:
        stats = await AnalysisService.get_platform_statistics()
        return {
            "success": True,
            "data": stats.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching platform stats: {str(e)}")


# ==================== STUDENT ANALYTICS (ADMIN VIEW) ====================

@router.get("/analytics/students")
async def get_all_students_analytics(
    class_filter: Optional[str] = Query(None, description="Filter by class"),
    sort_by: Optional[str] = Query("performance", description="Sort by: performance, name, class"),
    order: Optional[str] = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_admin: dict = Depends(get_current_admin)
):
    """
    Get analytics for all students.
    Admin can view performance metrics for all students with filters.
    """
    try:
        # Build filter query
        match_query = {}
        if class_filter:
            match_query["class"] = class_filter
        
        # Get all students
        students = await db.students.find(match_query).skip((page - 1) * limit).limit(limit).to_list(length=None)
        total_students = await db.students.count_documents(match_query)
        
        student_analytics = []
        for student in students:
            student_id = str(student["_id"])
            
            # Get quiz average
            quiz_pipeline = [
                {"$match": {"student_id": ObjectId(student_id)}},
                {"$group": {
                    "_id": None,
                    "avg_score": {"$avg": "$score"},
                    "total_quizzes": {"$sum": 1}
                }}
            ]
            quiz_result = await db.quiz_submissions.aggregate(quiz_pipeline).to_list(length=None)
            quiz_avg = quiz_result[0]["avg_score"] if quiz_result else 0
            total_quizzes = quiz_result[0]["total_quizzes"] if quiz_result else 0
            
            # Get exam average
            exam_pipeline = [
                {"$match": {"student_id": ObjectId(student_id)}},
                {"$project": {
                    "percentage": {
                        "$cond": [
                            {"$gt": ["$total_marks", 0]},
                            {"$multiply": [{"$divide": ["$total_score", "$total_marks"]}, 100]},
                            0
                        ]
                    }
                }},
                {"$group": {
                    "_id": None,
                    "avg_percentage": {"$avg": "$percentage"},
                    "total_exams": {"$sum": 1}
                }}
            ]
            exam_result = await db.exam_evaluations.aggregate(exam_pipeline).to_list(length=None)
            exam_avg = exam_result[0]["avg_percentage"] if exam_result else 0
            total_exams = exam_result[0]["total_exams"] if exam_result else 0
            
            # Calculate overall performance
            overall = (quiz_avg + exam_avg) / 2 if (quiz_avg or exam_avg) else 0
            
            # Get last activity
            last_activity = None
            last_quiz = await db.quiz_submissions.find_one(
                {"student_id": ObjectId(student_id)},
                sort=[("submitted_at", -1)]
            )
            last_exam = await db.exam_evaluations.find_one(
                {"student_id": ObjectId(student_id)},
                sort=[("created_at", -1)]
            )
            
            if last_quiz and last_exam:
                last_activity = max(
                    last_quiz.get("submitted_at", datetime.min),
                    last_exam.get("created_at", datetime.min)
                )
            elif last_quiz:
                last_activity = last_quiz.get("submitted_at")
            elif last_exam:
                last_activity = last_exam.get("created_at")
            
            student_analytics.append({
                "student_id": student_id,
                "student_name": student.get("student_name", "Unknown"),
                "class_name": student.get("class", "N/A"),
                "overall_performance": round(overall, 1),
                "quiz_average": round(quiz_avg, 1),
                "exam_average": round(exam_avg, 1),
                "total_quizzes": total_quizzes,
                "total_exams": total_exams,
                "last_activity": last_activity.isoformat() if last_activity else None,
                "engagement_score": round((total_quizzes + total_exams) / 10, 1)  # Simple engagement score
            })
        
        # Sort results
        if sort_by == "performance":
            student_analytics.sort(key=lambda x: x["overall_performance"], reverse=(order == "desc"))
        elif sort_by == "name":
            student_analytics.sort(key=lambda x: x["student_name"], reverse=(order == "desc"))
        
        return {
            "success": True,
            "data": {
                "students": student_analytics,
                "total": total_students,
                "page": page,
                "limit": limit,
                "total_pages": (total_students + limit - 1) // limit
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching student analytics: {str(e)}")


@router.get("/analytics/student/{student_id}")
async def get_single_student_analytics(
    student_id: str,
    period: PeriodType = Query(PeriodType.MONTH, description="Time period"),
    current_admin: dict = Depends(get_current_admin)
):
    """
    Get detailed analytics for a specific student.
    Admin can view comprehensive analytics for any student.
    """
    print(student_id)
    try:
        # Validate student_id format
        if not student_id or student_id == "undefined" or student_id == "null":
            raise HTTPException(status_code=400, detail="Please select a valid student")
        
        # Validate ObjectId format
        try:
            student_oid = ObjectId(student_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid student ID format")
        
        # Verify student exists
        student = await db.students.find_one({"_id": student_oid})
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        
        # Get overall score
        overall_score = await AnalysisService.get_student_overall_score(student_id, period)
        
        # Get streak
        streak = await AnalysisService.get_student_streak(student_id)
        
        # Get today's summary
        today_summary = await AnalysisService.get_today_summary(student_id)
        
        # Get quiz performance
        start_date, end_date = AnalysisService.get_date_range(period)
        quiz_submissions = await db.quiz_submissions.find({
            "student_id": ObjectId(student_id),
            "submitted_at": {"$gte": start_date, "$lte": end_date}
        }).to_list(length=None)
        
        quiz_scores = [sub["score"] for sub in quiz_submissions if "score" in sub]
        quiz_avg = sum(quiz_scores) / len(quiz_scores) if quiz_scores else 0
        
        # Get exam performance
        exam_evaluations = await db.exam_evaluations.find({
            "student_id": ObjectId(student_id),
            "created_at": {"$gte": start_date, "$lte": end_date}
        }).to_list(length=None)
        
        exam_scores = []
        for eva in exam_evaluations:
            if "total_score" in eva and "total_marks" in eva and eva["total_marks"] > 0:
                percentage = (eva["total_score"] / eva["total_marks"]) * 100
                exam_scores.append(percentage)
        
        exam_avg = sum(exam_scores) / len(exam_scores) if exam_scores else 0
        
        # Format recent quizzes for JSON response
        recent_quizzes_formatted = []
        for quiz in quiz_submissions[-5:]:  # Last 5
            recent_quizzes_formatted.append({
                "domain": quiz.get("domain", "Unknown"),
                "score": quiz.get("score", 0),
                "date": quiz.get("submitted_at", datetime.now(timezone.utc)).isoformat()
            })
        
        # Format recent exams for JSON response
        recent_exams_formatted = []
        for exam in exam_evaluations[-5:]:  # Last 5
            exam_percentage = 0
            if "total_score" in exam and "total_marks" in exam and exam["total_marks"] > 0:
                exam_percentage = (exam["total_score"] / exam["total_marks"]) * 100
            recent_exams_formatted.append({
                "subject": exam.get("paper_id", "Unknown"),
                "score": round(exam_percentage, 1),
                "date": exam.get("created_at", datetime.now(timezone.utc)).isoformat()
            })
        
        return {
            "success": True,
            "data": {
                "student_id": student_id,
                "student_name": student.get("student_name", "Unknown"),
                "class": student.get("class", "N/A"),
                "overall_score": overall_score.dict(),
                "streak": streak.dict(),
                "today_summary": today_summary.dict(),
                "quiz_performance": {
                    "total_quizzes": len(quiz_submissions),
                    "average_score": round(quiz_avg, 1),
                    "recent_quizzes": recent_quizzes_formatted
                },
                "exam_performance": {
                    "total_exams": len(exam_evaluations),
                    "average_score": round(exam_avg, 1),
                    "recent_exams": recent_exams_formatted
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching student analytics: {str(e)}")


# ==================== QUIZ ANALYTICS ====================

@router.get("/analytics/quiz-performance")
async def get_quiz_analytics(
    domain: Optional[str] = Query(None, description="Filter by domain"),
    class_filter: Optional[str] = Query(None, description="Filter by class"),
    period: PeriodType = Query(PeriodType.MONTH, description="Time period"),
    current_admin: dict = Depends(get_current_admin)
):
    """
    Get quiz performance analytics across the platform.
    Shows domain-wise statistics, average scores, etc.
    """
    try:
        start_date, end_date = AnalysisService.get_date_range(period)
        
        # Build match query
        match_query = {
            "submitted_at": {"$gte": start_date, "$lte": end_date}
        }
        if domain:
            match_query["domain"] = domain
        
        # Aggregate quiz data
        pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id": "$domain",
                "total_attempts": {"$sum": 1},
                "scores": {"$push": "$score"},
                "students": {"$addToSet": "$student_id"}
            }},
            {"$project": {
                "domain": "$_id",
                "total_attempts": 1,
                "average_score": {"$avg": "$scores"},
                "total_students": {"$size": "$students"},
                "min_score": {"$min": "$scores"},
                "max_score": {"$max": "$scores"}
            }},
            {"$sort": {"average_score": -1}}
        ]
        
        results = await db.quiz_submissions.aggregate(pipeline).to_list(length=None)
        
        return {
            "success": True,
            "data": {
                "period": period,
                "domain_analytics": [
                    {
                        "domain": r.get("domain", "Unknown"),
                        "total_attempts": r.get("total_attempts", 0),
                        "average_score": round(r.get("average_score", 0), 1),
                        "total_students": r.get("total_students", 0),
                        "min_score": round(r.get("min_score", 0), 1),
                        "max_score": round(r.get("max_score", 0), 1)
                    }
                    for r in results
                ]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching quiz analytics: {str(e)}")


# ==================== EXAM ANALYTICS ====================

@router.get("/analytics/exam-performance")
async def get_exam_analytics(
    subject: Optional[str] = Query(None, description="Filter by subject"),
    class_filter: Optional[str] = Query(None, description="Filter by class"),
    period: PeriodType = Query(PeriodType.MONTH, description="Time period"),
    current_admin: dict = Depends(get_current_admin)
):
    """
    Get exam performance analytics across the platform.
    Shows subject-wise statistics, score distributions, etc.
    """
    try:
        start_date, end_date = AnalysisService.get_date_range(period)
        
        # Get all exam evaluations
        match_query = {
            "created_at": {"$gte": start_date, "$lte": end_date}
        }
        
        exams = await db.exam_evaluations.find(match_query).to_list(length=None)
        
        # Calculate statistics
        total_exams = len(exams)
        scores = []
        for exam in exams:
            if "total_score" in exam and "total_marks" in exam and exam["total_marks"] > 0:
                percentage = (exam["total_score"] / exam["total_marks"]) * 100
                scores.append(percentage)
        
        avg_score = sum(scores) / len(scores) if scores else 0
        max_score = max(scores) if scores else 0
        min_score = min(scores) if scores else 0
        
        # Score distribution
        score_ranges = {"0-50": 0, "51-75": 0, "76-90": 0, "91-100": 0}
        for score in scores:
            if score <= 50:
                score_ranges["0-50"] += 1
            elif score <= 75:
                score_ranges["51-75"] += 1
            elif score <= 90:
                score_ranges["76-90"] += 1
            else:
                score_ranges["91-100"] += 1
        
        return {
            "success": True,
            "data": {
                "period": period,
                "total_exams": total_exams,
                "average_score": round(avg_score, 1),
                "highest_score": round(max_score, 1),
                "lowest_score": round(min_score, 1),
                "score_distribution": score_ranges,
                "unique_students": len(set([str(e.get("student_id")) for e in exams if e.get("student_id")]))
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching exam analytics: {str(e)}")


# ==================== ENGAGEMENT METRICS ====================

@router.get("/analytics/engagement")
async def get_engagement_metrics(
    period: PeriodType = Query(PeriodType.MONTH, description="Time period"),
    current_admin: dict = Depends(get_current_admin)
):
    """
    Get engagement metrics across different features.
    Shows usage statistics for quiz, exam, chat, AI tutor, etc.
    """
    try:
        start_date, end_date = AnalysisService.get_date_range(period)
        
        # Quiz engagement
        quiz_count = await db.quiz_submissions.count_documents({
            "submitted_at": {"$gte": start_date, "$lte": end_date}
        })
        
        quiz_users = await db.quiz_submissions.distinct("student_id", {
            "submitted_at": {"$gte": start_date, "$lte": end_date}
        })
        
        # Exam engagement
        exam_count = await db.exam_evaluations.count_documents({
            "created_at": {"$gte": start_date, "$lte": end_date}
        })
        
        exam_users = await db.exam_evaluations.distinct("student_id", {
            "created_at": {"$gte": start_date, "$lte": end_date}
        })
        
        # Chat engagement (if exists)
        chat_count = 0
        chat_users = []
        try:
            chat_count = await db.chat_messages.count_documents({
                "timestamp": {"$gte": start_date, "$lte": end_date}
            })
            chat_users = await db.chat_messages.distinct("student_id", {
                "timestamp": {"$gte": start_date, "$lte": end_date}
            })
        except:
            pass
        
        return {
            "success": True,
            "data": {
                "period": period,
                "quiz_engagement": {
                    "total_sessions": quiz_count,
                    "unique_users": len(quiz_users),
                    "avg_per_user": round(quiz_count / max(len(quiz_users), 1), 1)
                },
                "exam_engagement": {
                    "total_sessions": exam_count,
                    "unique_users": len(exam_users),
                    "avg_per_user": round(exam_count / max(len(exam_users), 1), 1)
                },
                "chat_engagement": {
                    "total_messages": chat_count,
                    "unique_users": len(chat_users),
                    "avg_per_user": round(chat_count / max(len(chat_users), 1), 1)
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching engagement metrics: {str(e)}")


# ==================== EXPORT / REPORTS ====================

@router.post("/analytics/export")
async def export_analytics_report(
    report_type: str = Query(..., description="Type: platform, students, quizzes, exams"),
    format: str = Query("json", description="Format: json, csv"),
    period: PeriodType = Query(PeriodType.MONTH, description="Time period"),
    current_admin: dict = Depends(get_current_admin)
):
    """
    Export analytics report in specified format.
    Currently supports JSON format. CSV can be added later.
    """
    try:
        if report_type == "platform":
            data = await AnalysisService.get_platform_statistics()
            return {
                "success": True,
                "report_type": "platform",
                "format": format,
                "data": data.dict(),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        
        # Add more report types as needed
        return {
            "success": True,
            "message": "Report export functionality - work in progress",
            "report_type": report_type
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting report: {str(e)}")
