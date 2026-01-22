# services/future_study_service.py
from datetime import datetime, timezone
from openai import OpenAI
import os
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
- Videos → ONLY available YouTube links
- Tutorials → ONLY available learning/tutorial websites
- Study centers → India-based institutions or programs
- NO explanations
- NO markdown
- NO extra text

RETURN STRICT JSON ONLY:

{{
  "youtube_videos": [
    {{"title": "", "link": ""}}
  ],
  "tutorial_links": [
    {{"title": "", "link": ""}}
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
