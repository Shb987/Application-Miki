# services/future_study_service.py
from datetime import datetime, timezone
from openai import OpenAI
import os
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY") or "sk-placeholder")

def extract_json(text: str):
    try:
        text = text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return None


async def generate_and_store_future_study(
    db,
    student_id: str,
    student_class: str,
    recommended_career,
    top_category: str
):
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

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    
    # Log usage
    if hasattr(response, 'usage') and response.usage:
        from app.utils.ai_usage_logger import log_ai_usage
        # Note: Future study currently uses synchronous client, but logger is async. 
        # However, it's called in an async context here.
        await log_ai_usage(student_id, "Future Study - Resources", "gpt-4.1-mini", response.usage)

    ai_text = response.output[0].content[0].text
    ai_data = extract_json(ai_text)

    if not ai_data:
        raise ValueError("Invalid AI JSON response")

    await db.future_study.update_one(
        {"student_id": student_id},
        {
            "$set": {
                "student_class": student_class,
                "recommended_career": recommended_career,
                "top_category": top_category,
                "resources": ai_data,
                "created_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    return ai_data
