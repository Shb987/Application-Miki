from fastapi import APIRouter, HTTPException
from openai import OpenAI
from bson import ObjectId
from dotenv import load_dotenv
from core.database import db
import os
import json
from datetime import datetime

# Load environment variables
load_dotenv()

router = APIRouter(
    tags=["User_Futurestudy Module"]
)

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------- Helper function ----------
def extract_json(text: str):
    try:
        text = text.strip()

        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == -1:
            return None

        return json.loads(text[start:end])
    except Exception:
        return None


# ---------- API ----------
@router.get("/{student_id}")
async def generate_future_study_guidance(student_id: str):

    # Fetch student details
    student = await db.students.find_one({"student_id": student_id})

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student_class = student.get("student_class")

    if not student_class:
        raise HTTPException(
            status_code=400,
            detail="Student class information missing"
        )

    # Fetch career analysis
    """
    Generate AI-based video, tutorial, and competitive exam
    recommendations based on student's recommended career.
    """

    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    # 1️⃣ Fetch latest career analysis for student
    record = await db.career_analyzer.find_one(
        {"student_id": s_oid},
        sort=[("timestamp", -1)]
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Career analysis not found"
        )

    recommended_career = record.get("recommended_career")
    top_category = record.get("top_category")

    if not recommended_career or not top_category:
        raise HTTPException(
            status_code=400,
            detail="Career data incomplete"
        )

    # ---------- PROMPT (AGE-AWARE & CAREER-AWARE) ----------
    prompt = f"""
You are an educational career guidance assistant for Indian school students.

STUDENT PROFILE:
- Current class: {student_class}
- Top intelligence category: {top_category}
- Recommended career: {recommended_career}

CORE REQUIREMENT:
Provide DETAILED, AGE-APPROPRIATE, and DIVERSE recommendations.

CLASS GUIDELINES:
- Class 1–5 → curiosity, awareness, basic concepts, fun learning
- Class 6–8 → foundations, skill exposure
- Class 9–10 → structured basics and entry-level exams
- Class 11–12 → subject depth and competitive exams

STRICT CONTENT RULES:
- NO advanced professional topics for junior classes
- NO medical/engineering syllabus for Class ≤7
- Content must be understandable at the student's level

RESOURCE QUANTITY (MANDATORY):
- YouTube videos → EXACTLY 5 items
- Tutorial links → EXACTLY 5 items
- Competitive exams → EXACTLY 5 items
- Study centers → EXACTLY 5 items

DIVERSITY RULES:
- Each YouTube video must focus on a DIFFERENT concept
- Tutorials must come from DIFFERENT platforms
- Exams must be beginner-friendly and India-based
- Study centers must support early-stage career exposure

RESOURCE RULES:
- Videos → ONLY YouTube links
- Tutorials → ONLY learning/tutorial websites
- Study centers → India-based institutions or programs
- NO explanations
- NO markdown
- NO extra text

RETURN STRICT JSON ONLY:

{{
  "youtube_videos": [
    {{
      "title": "",
      "link": ""
    }}
  ],
  "tutorial_links": [
    {{
      "title": "",
      "link": ""
    }}
  ],
  "competitive_exams": [
    {{
      "exam_name": "",
      "eligibility": "",
      "age_group": "",
      "description": ""
    }}
  ],
  "study_centers": [
    {{
      "center_name": "",
      "location": "",
      "career_focus": "",
      "description": ""
    }}
  ]
}}
"""

    # ---------- OpenAI Call ----------
    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )
        ai_content = response.output[0].content[0].text
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI API error: {str(e)}"
        )
    # 3️⃣ OpenAI call
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )

    # ---------- Parse JSON ----------
    ai_data = extract_json(ai_content)

    if not ai_data:
        raise HTTPException(
            status_code=500,
            detail="AI returned invalid JSON format"
        )

    # ---------- Save to DB ----------
    future_study_doc = {
        "student_id": student_id,
        "student_class": student_class,
        "recommended_career": recommended_career,
        "top_category": top_category,
        "resources": ai_data,
        "created_at": datetime.utcnow()
    }

    try:
        await db.future_study.insert_one(future_study_doc)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database insert failed: {str(e)}"
        )

    return {
        "message": "Class-appropriate future study guidance generated",
        "student_id": student_id,
        "student_class": student_class,
        "future_study": ai_data
    }