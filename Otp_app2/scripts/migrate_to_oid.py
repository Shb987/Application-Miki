import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

async def migrate_data():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "New_app")
    
    print(f"Connecting to: {mongo_uri}")
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    # 1. Map student_id (string) to _id (ObjectID)
    print("Fetching students...")
    students_cursor = db.students.find({}, {"_id": 1, "student_id": 1})
    student_map = {}
    async for s in students_cursor:
        if "student_id" in s:
            student_map[s["student_id"]] = s["_id"]
    
    print(f"Found {len(student_map)} students for mapping.")

    # 2. Update collections that reference student_id
    # We will add a new field 'student_oid' to store the ObjectID reference
    target_collections = {
        "evaluations": "student_id",
        "answers": "student_id",
        "career_analyzer": "student_id",
        "future_study_guidance": "student_id",
        "quiz_submissions": "user_id", # Based on previous audit, quiz uses user_id which might be student_id or mobile
        "notifications": "user_id"     # notification_service uses user_id
    }

    for coll_name, field in target_collections.items():
        print(f"\nProcessing collection: {coll_name}...")
        cursor = db[coll_name].find({field: {"$exists": True}})
        updated_count = 0
        
        async for doc in cursor:
            sid = doc.get(field)
            if sid in student_map:
                oid = student_map[sid]
                # Update the document with student_oid
                await db[coll_name].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"student_oid": oid}}
                )
                updated_count += 1
        
        print(f"✅ Updated {updated_count} documents in {coll_name}")

    # 3. Special case: usertable (Parent-Student links)
    print("\nProcessing usertable (Parent-Student links)...")
    user_cursor = db.usertable.find({"student_ids": {"$exists": True}})
    user_updated = 0
    async for user in user_cursor:
        s_ids = user.get("student_ids", [])
        o_ids = [student_map[sid] for sid in s_ids if sid in student_map]
        
        if o_ids:
            await db.usertable.update_one(
                {"_id": user["_id"]},
                {"$set": {"student_oids": o_ids}}
            )
            user_updated += 1
    
    print(f"✅ Updated {user_updated} users in usertable")
    print("\n--- Migration Phase 1 Complete ---")

if __name__ == "__main__":
    asyncio.run(migrate_data())
