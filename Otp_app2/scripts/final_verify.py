import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

async def final_verification():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "New_app")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    print("--- Final Verification Report (Single ObjectID System) ---")
    
    # 1. Check students
    student = await db.students.find_one()
    if student:
        if "student_id" not in student:
            print("✅ 'students' collection: No custom 'student_id' field. (Standard)")
        else:
            print(f"❌ 'students' collection: STILL HAS custom 'student_id': {student.get('student_id')}")

    # 2. Check usertable
    user = await db.usertable.find_one({"usertype": "parent"})
    if user:
        s_ids = user.get("student_ids", [])
        if s_ids and all(isinstance(sid, ObjectId) for sid in s_ids):
            print(f"✅ 'usertable': student_ids are all ObjectIDs. Sample: {s_ids}")
        elif not s_ids:
             print("⚠️ 'usertable': No students found for sample user, check manually.")
        else:
             print(f"❌ 'usertable': student_ids are NOT ObjectIDs: {[type(s) for s in s_ids]}")

    # 3. Check relational collections
    colls = ["evaluations", "answers", "notifications"]
    for c in colls:
        doc = await db[c].find_one()
        if doc:
            sid = doc.get("student_id")
            if isinstance(sid, ObjectId):
                print(f"✅ '{c}': student_id is an ObjectID: {sid}")
            else:
                print(f"❌ '{c}': student_id is {type(sid)} (expected ObjectID)")

if __name__ == "__main__":
    asyncio.run(final_verification())
