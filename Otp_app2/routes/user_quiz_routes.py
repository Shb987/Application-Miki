from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from bson import ObjectId
from datetime import datetime,timezone
import random

from core.database import db
from models.quiz_models import (
    QuizQuestionResponse, QuizSubmitRequest, QuizResultDetail,
    QuizAnswerSubmission
)
from utils.user_auth import get_current_user

router = APIRouter(tags=["Quiz Module - User"])

# Helper function to serialize question for user (without correct answer)
def serialize_question_for_user(question: dict) -> QuizQuestionResponse:
    """Convert MongoDB document to user-facing format (hides correct answer)"""
    return QuizQuestionResponse(
        question_id=str(question["_id"]),
        domain=question["domain"],
        question_text=question["question_text"],
        question_type=question["question_type"],
        options=question.get("options"),
        image_url=question.get("image_url"),
        difficulty_level=question["difficulty_level"],
        marks=question["marks"],
        hints=question.get("hints")
    )

# Helper to map class number to range
def determine_class_range(std: int) -> str:
    if 1 <= std <= 3:
        return "1-3"
    elif 4 <= std <= 5: # Assuming 3-5 covers 3,4,5 or per your seeds
        return "3-5"
    elif 6 <= std <= 8:
        return "6-8"
    elif 9 <= std <= 10:
        return "9-10"
    elif 11 <= std <= 12:
        return "11-12"
    return "6-8"  # Default fallback

# ==================== GET QUIZ QUESTIONS ====================
@router.get("/quiz/get-questions")
async def get_quiz_questions(
    student_class: int = Query(..., description="Student's class (e.g., 5, 8, 10)"),
    domain: Optional[str] = Query(None, description="Quiz domain (e.g., GK). If omitted or 'Mixed', selects from all."),
    difficulty_level: Optional[str] = Query(None, description="Easy, Medium, or Hard"),
    limit: int = Query(10, ge=1, le=50, description="Number of questions to fetch"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get random quiz questions for a student.
    - `student_class`: Pass the single class number (e.g., 5). The system auto-converts it to range (e.g., '3-5').
    - If `domain` is provided: Fetches questions from that specific domain.
    - If `domain` is 'Mixed' or omitted: Fetches random mixed questions from ALL domains.
    """
    # Auto-convert class number to range string
    class_range = determine_class_range(student_class)

    query = {
        "class_range": class_range,
        "is_active": True
    }
    
    # Filter by domain only if specified and not "Mixed"
    if domain and domain.lower() != "mixed":
        query["domain"] = domain
    
    if difficulty_level:
        query["difficulty_level"] = difficulty_level
    
    # Get total count
    total_available = await db.quiz_questions.count_documents(query)
    
    if total_available == 0:
        return {
            "status": "success",
            "message": "No questions available for the selected criteria",
            "total_available": 0,
            "data": []
        }
    
    # Fetch random questions
    # MongoDB aggregation for random sampling
    pipeline = [
        {"$match": query},
        {"$sample": {"size": min(limit, total_available)}}
    ]
    
    questions = await db.quiz_questions.aggregate(pipeline).to_list(length=limit)
    
    # Convert to user-facing format (hide correct answers)
    user_questions = [serialize_question_for_user(q) for q in questions]
    
    return {
        "status": "success",
        "message": f"Retrieved {len(user_questions)} questions",
        "total_available": total_available,
        "returned_count": len(user_questions),
        "data": user_questions
    }

# ==================== SUBMIT QUIZ ====================
@router.post("/quiz/submit")
async def submit_quiz(
    submission: QuizSubmitRequest,
    student_id: str = Query(..., description="Student ID associated with this submission"),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit quiz answers and get immediate results with scoring.
    """
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    # Fetch student details from DB
    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student_name = student.get("student_name", "Unknown Student")
    
    # We use the passed student_id
    s_oid = s_oid
    
    # Extract question IDs from submission
    question_ids = [ObjectId(ans.question_id) for ans in submission.answers]
    
    # Fetch all questions from database
    questions = await db.quiz_questions.find(
        {"_id": {"$in": question_ids}}
    ).to_list(length=len(question_ids))
    
    if len(questions) != len(submission.answers):
        raise HTTPException(
            status_code=400,
            detail="Some question IDs are invalid"
        )
    
    # Create a map for quick lookup
    questions_map = {str(q["_id"]): q for q in questions}
    
    # Evaluate answers
    total_marks = 0
    scored_marks = 0
    results = []
    user_answers_dict = {}
    
    for answer in submission.answers:
        question = questions_map.get(answer.question_id)
        if not question:
            continue
        
        user_answer = answer.user_answer.strip()
        correct_answer = question["correct_answer"].strip()
        
        # Case-insensitive comparison
        is_correct = user_answer.lower() == correct_answer.lower()
        
        marks_awarded = question["marks"] if is_correct else 0
        total_marks += question["marks"]
        scored_marks += marks_awarded
        
        user_answers_dict[answer.question_id] = user_answer
        
        results.append(QuizResultDetail(
            question_id=answer.question_id,
            question_text=question["question_text"],
            user_answer=user_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
            marks_awarded=marks_awarded,
            explanation=question.get("explanation")
        ))
    
    # Calculate percentage
    percentage = (scored_marks / total_marks * 100) if total_marks > 0 else 0
    
    # Save submission to database
    submission_doc = {
        "student_id": s_oid, 
        "student_name": student_name,
        "quiz_questions": [ans.question_id for ans in submission.answers],
        "user_answers": user_answers_dict,
        "score": scored_marks,
        "total_marks": total_marks,
        "percentage": round(percentage, 2),
        "domain": submission.domain,
        "class_range": submission.class_range,
        "submitted_at": datetime.now(timezone.utc)
    }
    
    result = await db.quiz_submissions.insert_one(submission_doc)
    submission_id = str(result.inserted_id)
    
    return {
        "status": "success",
        "message": "Quiz submitted successfully",
        "submission_id": submission_id,
        "summary": {
            "total_questions": len(submission.answers),
            "correct_count": sum(1 for r in results if r.is_correct),
            "score": scored_marks,
            "total_marks": total_marks,
            "percentage": round(percentage, 2)
        },
        "results": [r.dict() for r in results]
    }

# ==================== GET QUIZ RESULTS ====================
@router.get("/quiz/results/{submission_id}")
async def get_quiz_results(
    submission_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed results for a specific quiz submission.
    """
    try:
        submission = await db.quiz_submissions.find_one({"_id": ObjectId(submission_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid submission ID format")
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Verify user owns this submission (via mobile OR student_id)
    mobile_number = current_user.get("sub")
    student_id_str = current_user.get("student_id")
    
    if submission.get("mobile_number") != mobile_number and str(submission.get("student_id")) != student_id_str:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Fetch question details
    question_ids = [ObjectId(qid) for qid in submission["quiz_questions"]]
    questions = await db.quiz_questions.find(
        {"_id": {"$in": question_ids}}
    ).to_list(length=len(question_ids))
    
    questions_map = {str(q["_id"]): q for q in questions}
    
    # Build detailed results
    results = []
    for qid, user_answer in submission["user_answers"].items():
        question = questions_map.get(qid)
        if not question:
            continue
        
        is_correct = user_answer.lower() == question["correct_answer"].lower()
        marks_awarded = question["marks"] if is_correct else 0
        
        results.append({
            "question_id": qid,
            "question_text": question["question_text"],
            "user_answer": user_answer,
            "correct_answer": question["correct_answer"],
            "is_correct": is_correct,
            "marks_awarded": marks_awarded,
            "explanation": question.get("explanation")
        })
    
    submission["_id"] = str(submission["_id"])
    
    return {
        "status": "success",
        "data": {
            "submission": submission,
            "results": results
        }
    }

# ==================== GET QUIZ HISTORY ====================
@router.get("/quiz/history")
async def get_quiz_history(
    domain: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    Get user's quiz attempt history with optional domain filter.
    """
    # Get student_id from token
    student_id_str = current_user.get("student_id")
    mobile_number = current_user.get("sub")

    if student_id_str:
        query = {"student_id": ObjectId(student_id_str)}
    else:
        # Fallback for parent view/mixed history
        query = {"mobile_number": mobile_number}
        
    if domain:
        query["domain"] = domain
    
    total_count = await db.quiz_submissions.count_documents(query)
    
    submissions = await db.quiz_submissions.find(query)\
        .sort("submitted_at", -1)\
        .skip(skip)\
        .limit(limit)\
        .to_list(length=limit)
    
    # Serialize
    for sub in submissions:
        sub["_id"] = str(sub["_id"])
        sub["submission_id"] = sub["_id"]
    
    return {
        "status": "success",
        "total_count": total_count,
        "returned_count": len(submissions),
        "data": submissions
    }

# ==================== GET AVAILABLE DOMAINS ====================
@router.get("/quiz/available-domains")
async def get_available_domains(
    class_range: str = Query(..., description="User's class range"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of quiz domains available for the user's class.
    """
    domains = await db.quiz_questions.distinct(
        "domain",
        {"class_range": class_range, "is_active": True}
    )
    
    # Get question count per domain
    domain_counts = []
    for domain in domains:
        count = await db.quiz_questions.count_documents({
            "domain": domain,
            "class_range": class_range,
            "is_active": True
        })
        domain_counts.append({
            "domain": domain,
            "question_count": count
        })
    
    return {
        "status": "success",
        "class_range": class_range,
        "domains": sorted(domain_counts, key=lambda x: x["domain"])
    }

# ==================== GET LEADERBOARD ====================
@router.get("/quiz/leaderboard")
async def get_leaderboard(
    domain: Optional[str] = Query(None),
    class_range: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """
    Get top scorers leaderboard.
    Can be filtered by domain and class range.
    """
    match_query = {}
    if domain:
        match_query["domain"] = domain
    if class_range:
        match_query["class_range"] = class_range
    
    # Aggregate to get best scores per user
    pipeline = [
        {"$match": match_query},
        {"$sort": {"percentage": -1, "submitted_at": -1}},
        {"$group": {
            "_id": "$user_id",
            "student_name": {"$first": "$student_name"},
            "best_score": {"$first": "$score"},
            "best_percentage": {"$first": "$percentage"},
            "total_marks": {"$first": "$total_marks"},
            "domain": {"$first": "$domain"},
            "submitted_at": {"$first": "$submitted_at"}
        }},
        {"$sort": {"best_percentage": -1}},
        {"$limit": limit}
    ]
    
    leaderboard = await db.quiz_submissions.aggregate(pipeline).to_list(length=limit)
    
    # Add rank
    for idx, entry in enumerate(leaderboard):
        entry["rank"] = idx + 1
        entry["user_id"] = entry["_id"]
        del entry["_id"]
    
    return {
        "status": "success",
        "filters": {
            "domain": domain,
            "class_range": class_range
        },
        "leaderboard": leaderboard
    }

# ==================== GET USER STATS ====================
@router.get("/quiz/my-stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)):
    """
    Get user's quiz statistics - total quizzes taken, average score, etc.
    """
    student_id_str = current_user.get("student_id")
    mobile_number = current_user.get("sub")
    
    if student_id_str:
        match_query = {"student_id": ObjectId(student_id_str)}
    else:
        match_query = {"mobile_number": mobile_number}

    # Aggregate stats
    pipeline = [
        {"$match": match_query},
        {"$group": {
            "_id": None,
            "total_quizzes": {"$sum": 1},
            "total_score": {"$sum": "$score"},
            "total_marks": {"$sum": "$total_marks"},
            "avg_percentage": {"$avg": "$percentage"},
            "best_percentage": {"$max": "$percentage"}
        }}
    ]
    
    stats = await db.quiz_submissions.aggregate(pipeline).to_list(length=1)
    
    if not stats:
        return {
            "status": "success",
            "message": "No quiz attempts yet",
            "data": {
                "total_quizzes": 0,
                "total_score": 0,
                "total_marks": 0,
                "avg_percentage": 0,
                "best_percentage": 0
            }
        }
    
    stats_data = stats[0]
    del stats_data["_id"]
    
    # Round percentages
    stats_data["avg_percentage"] = round(stats_data["avg_percentage"], 2)
    stats_data["best_percentage"] = round(stats_data["best_percentage"], 2)
    
    # Get domain-wise breakdown
    domain_stats = await db.quiz_submissions.aggregate([
        {"$match": match_query},
        {"$group": {
            "_id": "$domain",
            "attempts": {"$sum": 1},
            "avg_percentage": {"$avg": "$percentage"}
        }}
    ]).to_list(length=None)
    
    stats_data["by_domain"] = [
        {
            "domain": item["_id"],
            "attempts": item["attempts"],
            "avg_percentage": round(item["avg_percentage"], 2)
        }
        for item in domain_stats
    ]
    
    return {
        "status": "success",
        "data": stats_data
    }
