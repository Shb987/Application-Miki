import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

async def fix_and_consolidate():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "New_app")
    
    print(f"Connecting to: {mongo_uri} | DB: {db_name}")
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    # 0. Drop conflicting index
    print("Dropping legacy unique index on students(student_id)...")
    try:
        await db.students.drop_index("student_id_1")
        print("✅ Index dropped.")
    except Exception as e:
        print(f"⚠️ Index drop error (might already be gone): {e}")

    # 1. Students Collection: Clean up custom string student_id
    print("Cleaning up 'students' collection...")
    await db.students.update_many({}, {"$unset": {"student_id": 1}})
    print("✅ Legacy 'student_id' removed from students.")

    # 2. Relational Collections: Rename student_oid -> student_id
    target_collections = [
        "evaluations",
        "answers",
        "career_analyzer",
        "future_study_guidance",
        "notifications",
        "quiz_submissions"
    ]

    for coll in target_collections:
        print(f"Consolidating collection: {coll}...")
        
        # Remove old string fields (student_id AND user_id)
        await db[coll].update_many({}, {"$unset": {"student_id": 1, "user_id": 1}})
        
        # Rename student_oid to student_id
        result = await db[coll].update_many(
            {"student_oid": {"$exists": True}},
            {"$rename": {"student_oid": "student_id"}}
        )
        print(f"✅ Consolidated {result.modified_count} records in {coll}")

    # 3. Usertable: Rename student_oids -> student_ids
    print("Consolidating 'usertable'...")
    await db.usertable.update_many({}, {"$unset": {"student_ids": 1}})
    await db.usertable.update_many(
        {"student_oids": {"$exists": True}},
        {"$rename": {"student_oids": "student_ids"}}
    )
    print("✅ Legacy 'student_ids' removed and 'student_oids' renamed to 'student_ids'.")

    # 4. Re-create non-unique indexes on the new unified student_id field
    print("Creating performance indexes...")
    for coll in target_collections:
        await db[coll].create_index("student_id")
    await db.usertable.create_index("student_ids")
    print("✅ Performance indexes created.")

    print("\n--- Database Consolidation Complete ---")

if __name__ == "__main__":
    asyncio.run(fix_and_consolidate())
