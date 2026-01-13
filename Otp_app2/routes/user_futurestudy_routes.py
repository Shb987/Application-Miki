from fastapi import APIRouter, HTTPException
from openai import OpenAI
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


# ---------- Helper function to safely extract JSON ----------
def extract_json(text: str):
    try:
        # Remove markdown code blocks if present
        if "" in text:
            text = text.split("")[1]

        # Extract JSON portion
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return None


# ---------- API Endpoint ----------
@router.get("/{student_id}")
async def generate_future_study_guidance(student_id: str):

    # Fetch latest career analysis
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

    if not recommended_career or not top_category:
        raise HTTPException(
            status_code=400,
            detail="Career data incomplete"
        )

    # Prompt
    prompt = f"""
You are an educational career guidance assistant.

Student Information:
- Top intelligence category: {top_category}
- Recommended career(s): {recommended_career}

TASK:
Provide ONLY verified online learning links and competitive exam details
suitable for SCHOOL STUDENTS in India.

RULES:
- Video resources → ONLY YouTube links
- Tutorial resources → ONLY learning/tutorial links
- Exams must be India-based and school-level
- No explanations outside JSON
- No markdown, no extra text

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
  ]
}}
"""

    # OpenAI call (LATEST API – STABLE)
    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )
        ai_content = response.output_text
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI API error: {str(e)}"
        )

    # Parse AI JSON safely
    ai_data = extract_json(ai_content)

    if not ai_data:
        raise HTTPException(
            status_code=500,
            detail="AI returned invalid JSON format"
        )

    # Save to MongoDB (future_study collection)
    future_study_doc = {
        "student_id": student_id,
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

    # Success response
    return {
        "message": "Future study guidance generated successfully",
        "student_id": student_id,
        "future_study": ai_data
    }