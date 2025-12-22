from fastapi import APIRouter, HTTPException
from openai import OpenAI
from dotenv import load_dotenv
from core.database import db
import os

# Load environment variables
load_dotenv()

router = APIRouter(
    tags=["User_Futurestudy Module"]
)

# Initialize OpenAI client using .env key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@router.get("/{student_id}")
async def generate_future_study_guidance(student_id: str):
    """
    Generate AI-based video, tutorial, and competitive exam
    recommendations based on student's recommended career.
    """

    # 1️⃣ Fetch latest career analysis for student
    record = await db.career_analyzer.find_one(
        {"student_id": student_id},
        sort=[("timestamp", -1)]
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Career analysis not found for this student"
        )

    recommended_career = record.get("recommended_career")
    top_category = record.get("top_category")

    if not recommended_career:
        raise HTTPException(
            status_code=400,
            detail="Recommended career not available"
        )

    # 2️⃣ OpenAI prompt
    prompt = f"""
You are an expert educational career guidance system.
Top intelligence category: {top_category}
Recommended career(s): {recommended_career}

Generate the following in SIMPLE language suitable for school students:

1. Video learning suggestions (mention platforms like YouTube, Khan Academy)
2. Tutorials / learning roadmap
3. Competitive exams related to this career
   (India-focused, age-appropriate, future-oriented)

Rules:
- Avoid college-only exams for children
- Avoid technical jargon
- Keep recommendations practical

Return STRICT JSON only in this format:

{{
  "videos": [],
  "tutorials": [],
  "competitive_exams": []
}}
"""

    # 3️⃣ OpenAI call
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )

    ai_result = response.choices[0].message.content

    # 4️⃣ API response
    return {
        "student_id": student_id,
        "recommended_career": recommended_career,
        "top_category": top_category,
        "ai_recommendations": ai_result
    }
