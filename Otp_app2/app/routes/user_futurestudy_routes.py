from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from dotenv import load_dotenv
from app.core.database import db
from app.utils.user_auth import get_current_user
from app.utils.usage_guard import has_premium_access
from app.services.future_study_service import generate_and_store_future_study

# Load environment variables
load_dotenv()

async def check_premium(student_id: str):
    if not await has_premium_access(student_id):
        raise HTTPException(status_code=403, detail="Career & Study Roadmap is a Premium feature. Please upgrade to Plus or Pro.")

router = APIRouter(
    tags=["User_Futurestudy Module"]
)

@router.get("/{student_id}")
@router.get("/future-study/{student_id}")
async def generate_future_study_guidance(student_id: str, current_user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(student_id):
        raise HTTPException(status_code=404, detail="Invalid student_id format")
    await check_premium(student_id)

    # Fetch student details
    student = await db.students.find_one({"student_id": student_id})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student_class = student.get("student_class")
    if not student_class:
        raise HTTPException(status_code=400, detail="Student class information missing")

    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    # 1. Fetch latest career analysis for student
    record = await db.career_analyzer.find_one(
        {"student_id": {"$in": [s_oid, str(s_oid)]}},
        sort=[("timestamp", -1)]
    )
    if not record:
        raise HTTPException(status_code=404, detail="Career analysis not found")

    scores = record.get("scores", {})
    percentages = record.get("percentages", {})
    from app.routes.user_routes import get_top_5_careers_with_scores, resolve_top_categories, get_recommended_career
    resolved_cats, top_category = resolve_top_categories(scores, percentages, record.get("top_category"))
    top_5_items, top_5_str, _ = get_top_5_careers_with_scores(scores, percentages, top_categories=resolved_cats)
    recommended_career = top_5_str or record.get("recommended_career") or get_recommended_career(top_category)

    if not recommended_career or not top_category:
        raise HTTPException(status_code=400, detail="Career data incomplete")

    # 2. Generate/retrieve clean resources via future_study_service (No hallucinated URLs)
    resources = await generate_and_store_future_study(
        db=db,
        student_id=student_id,
        student_class=str(student_class),
        recommended_career=recommended_career,
        top_category=top_category
    )

    return {
        "status_code": 200,
        "message": "Class-appropriate future study guidance generated",
        "student_id": student_id,
        "student_class": str(student_class),
        "top_category": top_category,
        "recommended_career": recommended_career,
        "future_study": resources
    }
