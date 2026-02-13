from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from bson import ObjectId
from datetime import datetime,timezone
import random

from app.core.database import db
from app.models.quiz_models import (
    QuizQuestionResponse, QuizSubmitRequest, QuizResultDetail,
    QuizAnswerSubmission
)
from app.utils.user_auth import get_current_user

router = APIRouter(tags=["Quiz Module - User"])

# Helper to map domain to static images
DOMAIN_IMAGE_MAPPING = {
    "English": "english.png",
    "GK": "gk.png",
    "General": "gk.png",
    "History": "gk.png",
    "Economics": "gk.png",
    "Grammar": "grammar.png",
    "IT": "it.png",
    "Literature": "literature.png",
    "Logic": "logic.png",
    "Advanced": "logic.png",
    "Mathematics": "maths.png",
    "Science": "science.png",
    "Biology": "science.png",
    "Chemistry": "science.png",
    "Physics": "science.png",
    "Sports": "sports.png"
}

# Helper function to serialize question for user (without correct answer)
def serialize_question_for_user(question: dict) -> QuizQuestionResponse:
    """Convert MongoDB document to user-facing format (hides correct answer)"""
    domain = question.get("domain", "GK")
    
    # Logic: Use database image if available, else fallback to domain mapping, else gk.png
    image_url = question.get("image_url")
    if not image_url:
        image_filename = DOMAIN_IMAGE_MAPPING.get(domain, "gk.png")
        image_url = f"Domain_pictures/{image_filename}"

    return QuizQuestionResponse(
        question_id=str(question["_id"]),
        domain=domain,
        question_text=question["question_text"],
        question_type=question["question_type"],
        options=question.get("options"),
        image_url=image_url,
        difficulty_level=question["difficulty_level"],
        marks=question["marks"],
        correct_answer=question["correct_answer"]
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
    difficulty_level: Optional[str] = Query(None, description="Easy, Medium, or Hard"),
    limit: int = Query(20, ge=1, le=50, description="Number of questions to fetch"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get random quiz questions for a student.
    - `student_class`: Pass the single class number (e.g., 5). The system auto-converts it to range (e.g., '3-5').
    - Fetches random mixed questions from ALL domains by default for the 'Game' mode.
    """
    # Auto-convert class number to range string
    class_range = determine_class_range(student_class)

    query = {
        "class_range": class_range,
        "is_active": True
    }
    
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
    difficulty_level: str = Query(..., description="Difficulty of the quiz (Easy, Medium, Hard)"),
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
        
        user_index = answer.user_answer_index
        correct_index = question.get("correct_answer")
        
        is_correct = user_index == correct_index
        
        marks_awarded = question["marks"] if is_correct else 0
        total_marks += question["marks"]
        scored_marks += marks_awarded
        
        user_answers_dict[answer.question_id] = user_index
        
        results.append(QuizResultDetail(
            question_id=answer.question_id,
            question_text=question["question_text"],
            user_answer_index=user_index,
            correct_answer_index=correct_index,
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
        "domain": "Mixed",
        "difficulty_level": difficulty_level,
        "student_class": submission.student_class,
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

# ==================== GET QUIZ HISTORY ====================
@router.get("/quiz/history")
async def get_quiz_history(
    student_id: str = Query(..., description="Student ID to fetch history for"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    Get quiz attempt history for a specific student.
    Filters by student_id passed in query.
    Returns only summary results, not detailed answers.
    """
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    # Filter strictly by student_id
    query = {"student_id": s_oid}
    
    total_count = await db.quiz_submissions.count_documents(query)
    
    # Exclude detailed arrays and domain to save bandwidth, include difficulty_level
    projection = {"quiz_questions": 0, "user_answers": 0, "domain": 0}
    
    submissions = await db.quiz_submissions.find(query, projection)\
        .sort("submitted_at", -1)\
        .skip(skip)\
        .limit(limit)\
        .to_list(length=limit)
    
    # Serialize ObjectIds to strings
    for sub in submissions:
        sub["_id"] = str(sub["_id"])
        sub["submission_id"] = sub["_id"]
        # Ensure student_id is also a string if present
        if "student_id" in sub:
            sub["student_id"] = str(sub["student_id"])
    
    return {
        "status": "success",
        "total_count": total_count,
        "returned_count": len(submissions),
        "data": submissions
    }


# ==================== GET LEADERBOARD ====================
@router.get("/quiz/leaderboard")
async def get_leaderboard(
    student_class: Optional[int] = Query(None, description="Filter by specific class (e.g. 5)"),
    difficulty_level: Optional[str] = Query(None, description="Filter by difficulty (Easy, Medium, Hard)"),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """
    Get top scorers leaderboard.
    Groups by student_id to show individual student rankings.
    Can be filtered by student_class and difficulty_level.
    """
    match_query = {}
    if student_class:
        match_query["student_class"] = student_class
    if difficulty_level:
        match_query["difficulty_level"] = difficulty_level
    
    # Aggregate to get best scores per STUDENT (not user)
    pipeline = [
        {"$match": match_query},
        {"$sort": {"percentage": -1, "submitted_at": -1}},
        {"$group": {
            "_id": "$student_id",
            "student_name": {"$first": "$student_name"},
            "best_score": {"$first": "$score"},
            "best_percentage": {"$first": "$percentage"},
            "total_marks": {"$first": "$total_marks"},
            "difficulty_level": {"$first": "$difficulty_level"},
            "submitted_at": {"$first": "$submitted_at"}
        }},
        # Join with students collection to get profile picture
        {
            "$lookup": {
                "from": "students",
                "localField": "_id",
                "foreignField": "_id",
                "as": "student_info"
            }
        },
        {
            "$addFields": {
                "image_url": {"$arrayElemAt": ["$student_info.image_url", 0]}
            }
        },
        {"$project": {"student_info": 0}},
        {"$sort": {"best_percentage": -1}},
        {"$limit": limit}
    ]
    
    leaderboard = await db.quiz_submissions.aggregate(pipeline).to_list(length=limit)
    
    # Add rank and serialize IDs
    for idx, entry in enumerate(leaderboard):
        entry["rank"] = idx + 1
        # Convert _id (which is student_id) to string
        entry["student_id"] = str(entry["_id"])
        del entry["_id"]
    
    return {
        "status": "success",
        "filters": {
            "student_class": student_class
        },
        "leaderboard": leaderboard
    }

# ==================== GET USER STATS ====================
@router.get("/quiz/my-stats")
async def get_user_stats(
    student_id: str = Query(..., description="Student ID to fetch stats for"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get quiz statistics for a specific student.
    Strictly filters by student_id.
    """
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    match_query = {"student_id": s_oid}

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
    
    # Get difficulty-wise breakdown
    difficulty_stats = await db.quiz_submissions.aggregate([
        {"$match": match_query},
        {"$group": {
            "_id": "$difficulty_level",
            "attempts": {"$sum": 1},
            "avg_percentage": {"$avg": "$percentage"}
        }}
    ]).to_list(length=None)
    
    stats_data["by_difficulty"] = [
        {
            "difficulty": item["_id"] if item["_id"] else "Unknown",
            "attempts": item["attempts"],
            "avg_percentage": round(item["avg_percentage"], 2)
        }
        for item in difficulty_stats
    ]
    
    return {
        "status": "success",
        "data": stats_data
    }
