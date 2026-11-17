import asyncio
import os
import sys

# Ensure root of project is in python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.database import db

TARGET_COLLECTIONS = [
    "wordle_questions",
    "squares_questions",
    "wordle_sessions",
    "squares_sessions",
    "quiz_questions",
]

async def migrate():
    print("=" * 60)
    print("MIGRATION: Updating class_range '3-5' to '4-5' across database")
    print("=" * 60)

    all_colls = await db.list_collection_names()
    target_set = set(TARGET_COLLECTIONS).union(all_colls)

    total_modified = 0
    for coll_name in sorted(target_set):
        try:
            coll = db[coll_name]
            count_old = await coll.count_documents({"class_range": "3-5"})
            if count_old > 0:
                result = await coll.update_many(
                    {"class_range": "3-5"},
                    {"$set": {"class_range": "4-5"}}
                )
                print(f"[UPDATED] {coll_name}: matched {result.matched_count}, modified {result.modified_count}")
                total_modified += result.modified_count
            else:
                if coll_name in TARGET_COLLECTIONS:
                    count_new = await coll.count_documents({"class_range": "4-5"})
                    print(f"[OK] {coll_name}: 0 remaining '3-5', current '4-5': {count_new}")
        except Exception as e:
            if coll_name in TARGET_COLLECTIONS:
                print(f"[ERROR] {coll_name}: {e}")

    print("-" * 60)
    print(f"Migration completed successfully. Total records updated: {total_modified}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(migrate())
