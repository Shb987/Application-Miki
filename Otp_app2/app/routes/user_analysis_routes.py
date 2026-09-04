from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId

from app.utils.user_auth import get_current_user
from app.services.analysis_service import AnalysisService
from app.models.analysis_models import (
    VisualCoreDashboard, VisualCareerAnalytics, 
    VisualExamAnalytics, VisualQuizAnalytics
)
from app.core.database import db

router = APIRouter(prefix="/analytics")

@router.get("/visual/dashboard", response_model=VisualCoreDashboard)
@router.get("/visual/dashboard/", response_model=VisualCoreDashboard, include_in_schema=False)
async def get_visual_core_dashboard(
    student_id: Optional[str] = Query(None, description="Optional target Student ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    📊 The Master Visual Dashboard Aggregator.
    Returns Careers, Exams, and Quizzes with charting data in one call.
    """
    try:
        target_id = student_id if student_id else str(current_user["_id"])
        
        # Get student details safely
        student = None
        if ObjectId.is_valid(target_id):
            student = await db.students.find_one({"_id": ObjectId(target_id)})
        if not student:
            student = await db.students.find_one({"student_id": target_id})
            
        student_name = student.get("student_name", "Learner") if student else "Learner"

        return await AnalysisService.get_visual_dashboard(target_id, student_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visual Dashboard Error: {str(e)}")

@router.get("/visual/career", response_model=Optional[VisualCareerAnalytics])
@router.get("/visual/career/", response_model=Optional[VisualCareerAnalytics], include_in_schema=False)
async def get_visual_career_analysis(
    student_id: str = Query(..., description="Target Student ID"),
    current_user: dict = Depends(get_current_user)
):
    """Intelligence score breakdown for Radar/Bar charts"""
    try:
        if not ObjectId.is_valid(student_id):
            raise HTTPException(status_code=400, detail="Invalid student_id format")
        return await AnalysisService.get_visual_career_stats(ObjectId(student_id))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visual Career Error: {str(e)}")

@router.get("/visual/exam", response_model=Optional[VisualExamAnalytics])
@router.get("/visual/exam/", response_model=Optional[VisualExamAnalytics], include_in_schema=False)
async def get_visual_exam_analysis(
    student_id: str = Query(..., description="Target Student ID"),
    current_user: dict = Depends(get_current_user)
):
    """Historical progression trend for Line charts"""
    try:
        if not ObjectId.is_valid(student_id):
            raise HTTPException(status_code=400, detail="Invalid student_id format")
        return await AnalysisService.get_visual_exam_stats(ObjectId(student_id))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visual Exam Error: {str(e)}")

@router.get("/visual/quiz", response_model=Optional[VisualQuizAnalytics])
@router.get("/visual/quiz/", response_model=Optional[VisualQuizAnalytics], include_in_schema=False)
async def get_visual_quiz_analysis(
    student_id: str = Query(..., description="Target Student ID"),
    current_user: dict = Depends(get_current_user)
):
    """Difficulty breakdown and trend for 'Mixed' quizzes"""
    try:
        if not ObjectId.is_valid(student_id):
            raise HTTPException(status_code=400, detail="Invalid student_id format")
        return await AnalysisService.get_visual_quiz_stats(ObjectId(student_id))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visual Quiz Error: {str(e)}")

