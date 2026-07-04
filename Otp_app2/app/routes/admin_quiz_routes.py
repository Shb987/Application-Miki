from fastapi import APIRouter, HTTPException, Depends, Body, Query
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
import json

from app.core.database import db
from app.models.quiz_models import (
    QuizQuestion, QuestionType, DifficultyLevel, ClassRange,
    QuizFilter
)
from app.utils.admin_auth import require_permission

router = APIRouter(tags=["Quiz Module - Admin"])

# Helper function to serialize MongoDB ObjectId
def serialize_question(question: dict) -> dict:
    """Convert MongoDB document to JSON-serializable format"""
    if "_id" in question:
        question["question_id"] = str(question["_id"])
        del question["_id"]
    return question

# ==================== ADD QUESTION ====================
@router.post("/quiz/add-question")
async def add_quiz_question(
    question: QuizQuestion,
    current_admin: dict = Depends(require_permission("Quizzes", "create"))
):
    """
    Add a new quiz question to the database.
    Admin only endpoint.
    """
    question_dict = question.dict()
    question_dict["created_by"] = current_admin.get("admin_id", "unknown")
    question_dict["created_at"] = datetime.utcnow()
    question_dict["updated_at"] = datetime.utcnow()
    
    # Validate question type specific requirements
    if question.question_type in [QuestionType.MCQ, QuestionType.ANALOGY]:
        if not question.options or len(question.options) < 2:
            raise HTTPException(
                status_code=400,
                detail=f"{question.question_type} requires at least 2 options"
            )
    
    result = await db.quiz_questions.insert_one(question_dict)
    
    question_dict["question_id"] = str(result.inserted_id)
    del question_dict["_id"]
    
    return {
        "status": "success",
        "message": "Quiz question added successfully",
        "data": question_dict
    }

# ==================== GET ALL QUESTIONS ====================
@router.get("/quiz/questions")
async def get_quiz_questions(
    domain: Optional[str] = Query(None),
    class_range: Optional[str] = Query(None),
    difficulty_level: Optional[str] = Query(None),
    question_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_admin: dict = Depends(require_permission("Quizzes", "read"))
):
    """
    Get all quiz questions with optional filters.
    Supports pagination.
    """
    query = {}
    
    if domain:
        query["domain"] = domain
    if class_range:
        query["class_range"] = class_range
    if difficulty_level:
        query["difficulty_level"] = difficulty_level
    if question_type:
        query["question_type"] = question_type
    if is_active is not None:
        query["is_active"] = is_active
    
    total_count = await db.quiz_questions.count_documents(query)
    
    questions = await db.quiz_questions.find(query).skip(skip).limit(limit).to_list(length=limit)
    
    serialized_questions = [serialize_question(q) for q in questions]
    
    return {
        "status": "success",
        "total_count": total_count,
        "returned_count": len(serialized_questions),
        "skip": skip,
        "limit": limit,
        "data": serialized_questions
    }

# ==================== GET SINGLE QUESTION ====================
@router.get("/quiz/question/{question_id}")
async def get_quiz_question(
    question_id: str,
    current_admin: dict = Depends(require_permission("Quizzes", "read"))
):
    """Get a single quiz question by ID"""
    try:
        question = await db.quiz_questions.find_one({"_id": ObjectId(question_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid question ID format")
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    return {
        "status": "success",
        "data": serialize_question(question)
    }

# ==================== UPDATE QUESTION ====================
@router.put("/quiz/update-question/{question_id}")
async def update_quiz_question(
    question_id: str,
    question: QuizQuestion,
    current_admin: dict = Depends(require_permission("Quizzes", "update"))
):
    """Update an existing quiz question"""
    try:
        existing = await db.quiz_questions.find_one({"_id": ObjectId(question_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid question ID format")
    
    if not existing:
        raise HTTPException(status_code=404, detail="Question not found")
    
    question_dict = question.dict()
    question_dict["updated_at"] = datetime.utcnow()
    question_dict["updated_by"] = current_admin.get("admin_id", "unknown")
    
    # Preserve original creation metadata
    question_dict["created_at"] = existing.get("created_at")
    question_dict["created_by"] = existing.get("created_by")
    
    await db.quiz_questions.update_one(
        {"_id": ObjectId(question_id)},
        {"$set": question_dict}
    )
    
    return {
        "status": "success",
        "message": "Question updated successfully",
        "data": serialize_question({**question_dict, "_id": ObjectId(question_id)})
    }

# ==================== DELETE QUESTION ====================
@router.delete("/quiz/delete-question/{question_id}")
async def delete_quiz_question(
    question_id: str,
    hard_delete: bool = Query(False, description="Permanently delete instead of soft delete"),
    current_admin: dict = Depends(require_permission("Quizzes", "delete"))
):
    """
    Delete a quiz question.
    By default, performs soft delete (sets is_active=False).
    Use hard_delete=true for permanent deletion.
    """
    try:
        existing = await db.quiz_questions.find_one({"_id": ObjectId(question_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid question ID format")
    
    if not existing:
        raise HTTPException(status_code=404, detail="Question not found")
    
    if hard_delete:
        await db.quiz_questions.delete_one({"_id": ObjectId(question_id)})
        message = "Question permanently deleted"
    else:
        await db.quiz_questions.update_one(
            {"_id": ObjectId(question_id)},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )
        message = "Question deactivated (soft delete)"
    
    return {
        "status": "success",
        "message": message
    }

# ==================== BULK UPLOAD ====================
@router.post("/quiz/bulk-upload")
async def bulk_upload_questions(
    questions: List[QuizQuestion],
    current_admin: dict = Depends(require_permission("Quizzes", "create"))
):
    """
    Bulk upload multiple quiz questions.
    Accepts a JSON array of questions.
    """
    if not questions:
        raise HTTPException(status_code=400, detail="No questions provided")
    
    admin_id = current_admin.get("admin_id", "unknown")
    current_time = datetime.utcnow()
    
    questions_to_insert = []
    for question in questions:
        question_dict = question.dict()
        question_dict["created_by"] = admin_id
        question_dict["created_at"] = current_time
        question_dict["updated_at"] = current_time
        questions_to_insert.append(question_dict)
    
    result = await db.quiz_questions.insert_many(questions_to_insert)
    
    return {
        "status": "success",
        "message": f"Successfully uploaded {len(result.inserted_ids)} questions",
        "inserted_count": len(result.inserted_ids),
        "question_ids": [str(id) for id in result.inserted_ids]
    }

# ==================== GET DOMAINS ====================
@router.get("/quiz/domains")
async def get_quiz_domains(current_admin: dict = Depends(require_permission("Quizzes", "read"))):
    """Get list of all available quiz domains"""
    domains = await db.quiz_questions.distinct("domain", {"is_active": True})
    return {
        "status": "success",
        "domains": sorted(domains)
    }

# ==================== GET STATISTICS ====================
@router.get("/quiz/statistics")
async def get_quiz_statistics(current_admin: dict = Depends(require_permission("Quizzes", "read"))):
    """Get quiz statistics - total questions per domain, class, difficulty, etc."""
    
    # Aggregate by domain
    domain_stats = await db.quiz_questions.aggregate([
        {"$match": {"is_active": True}},
        {"$group": {"_id": "$domain", "count": {"$sum": 1}}}
    ]).to_list(length=None)
    
    # Aggregate by class range
    class_stats = await db.quiz_questions.aggregate([
        {"$match": {"is_active": True}},
        {"$group": {"_id": "$class_range", "count": {"$sum": 1}}}
    ]).to_list(length=None)
    
    # Aggregate by difficulty
    difficulty_stats = await db.quiz_questions.aggregate([
        {"$match": {"is_active": True}},
        {"$group": {"_id": "$difficulty_level", "count": {"$sum": 1}}}
    ]).to_list(length=None)
    
    # Aggregate by question type
    type_stats = await db.quiz_questions.aggregate([
        {"$match": {"is_active": True}},
        {"$group": {"_id": "$question_type", "count": {"$sum": 1}}}
    ]).to_list(length=None)
    
    total_questions = await db.quiz_questions.count_documents({"is_active": True})
    total_submissions = await db.quiz_submissions.count_documents({})
    
    return {
        "status": "success",
        "data": {
            "total_questions": total_questions,
            "total_submissions": total_submissions,
            "by_domain": {item["_id"]: item["count"] for item in domain_stats},
            "by_class_range": {item["_id"]: item["count"] for item in class_stats},
            "by_difficulty": {item["_id"]: item["count"] for item in difficulty_stats},
            "by_question_type": {item["_id"]: item["count"] for item in type_stats}
        }
    }
