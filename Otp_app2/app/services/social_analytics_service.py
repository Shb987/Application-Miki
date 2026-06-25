from app.core.database import db
from typing import List
import asyncio

async def process_content_interaction(student_id: str, skill_tags: List[str]):
    """
    Background task to update the student's skill profile based on interaction.
    """
    if not skill_tags:
        return
    
    # We will increment the score for each tag by 1 for view, or we can use weighted logic.
    # For now, let's assume each interaction (like/view) adds +1 to the tag's skill_profile score.
    
    # We can use MongoDB's $inc operator to efficiently update multiple keys in the dictionary.
    inc_query = {}
    for tag in skill_tags:
        # e.g., skill_profile.robotics: 1
        tag_lower = tag.lower().strip()
        if tag_lower:
            inc_query[f"skill_profile.{tag_lower}"] = 1
            
    if inc_query:
        try:
            await db.students.update_one(
                {"_id": student_id},
                {"$inc": inc_query}
            )
            print(f"✅ Updated skill_profile for student {student_id} with tags: {skill_tags}")
        except Exception as e:
            print(f"❌ Error updating skill profile for student {student_id}: {e}")
