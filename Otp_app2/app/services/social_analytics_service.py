from app.core.database import db
from typing import List

# Weighted scoring by interaction type (higher = stronger intent signal)
INTERACTION_WEIGHTS = {
    "view": 1,
    "like": 2,
    "share": 3,  # Sharing is the strongest intent signal
}

async def process_content_interaction(student_id: str, skill_tags: List[str], interaction_type: str = "view"):
    """
    Background task to update the student's skill profile based on interaction.
    Uses weighted scoring: view=+1, like=+2, share=+3
    """
    if not skill_tags:
        return

    weight = INTERACTION_WEIGHTS.get(interaction_type, 1)

    # Use MongoDB's $inc operator to efficiently update multiple keys in the dictionary.
    inc_query = {}
    for tag in skill_tags:
        tag_lower = tag.lower().strip()
        if tag_lower:
            inc_query[f"skill_profile.{tag_lower}"] = weight

    if inc_query:
        try:
            await db.students.update_one(
                {"_id": student_id},
                {"$inc": inc_query}
            )
            print(f"✅ Updated skill_profile for student {student_id} | type={interaction_type} | weight={weight} | tags={skill_tags}")
        except Exception as e:
            print(f"❌ Error updating skill profile for student {student_id}: {e}")

