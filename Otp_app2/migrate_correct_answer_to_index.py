
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
DB_NAME = os.getenv("DB_NAME", "new_app2")

async def migrate_correct_answers():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    print("--- STARTING MIGRATION: STRING TO INDEX ---")
    
    questions = await db.quiz_questions.find({}).to_list(None)
    total = len(questions)
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    for q in questions:
        current_ans = q.get("correct_answer")
        options = q.get("options", [])
        
        # If already an int, skip (though some might be strings like "1")
        if isinstance(current_ans, int):
            skipped_count += 1
            continue
            
        if not options:
            # Special case for non-MCQ if we have any?
            # For now, let's assume all have options or are strings we can't map
            print(f"Skipping Q (no options): {q.get('question_text')[:50]}")
            skipped_count += 1
            continue

        # Try to find the index (1-based)
        try:
            # Clean string comparison
            idx = -1
            clean_ans = str(current_ans).strip().lower()
            for i, opt in enumerate(options):
                if str(opt).strip().lower() == clean_ans:
                    idx = i + 1
                    break
            
            if idx != -1:
                await db.quiz_questions.update_one(
                    {"_id": q["_id"]},
                    {"$set": {"correct_answer": idx}}
                )
                updated_count += 1
            else:
                # If it's something like "True" / "False" but options are different
                # Or if it's already a number string "1"
                if str(current_ans).isdigit():
                    val = int(current_ans)
                    if 1 <= val <= len(options):
                         await db.quiz_questions.update_one(
                            {"_id": q["_id"]},
                            {"$set": {"correct_answer": val}}
                        )
                         updated_count += 1
                    else:
                        print(f"Could not map digit answer {current_ans} for Q: {q.get('question_text')[:50]}")
                        error_count += 1
                else:
                    print(f"FAILED TO MAP: '{current_ans}' not in {options} for Q: {q.get('question_text')[:50]}")
                    error_count += 1
        except Exception as e:
            print(f"Error migrating Q {q['_id']}: {e}")
            error_count += 1

    print(f"\nMigration Complete:")
    print(f"Total: {total}")
    print(f"Updated: {updated_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Errors/Failed: {error_count}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(migrate_correct_answers())
