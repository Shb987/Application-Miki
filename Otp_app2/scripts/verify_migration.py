import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def verify_migration():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "New_app")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    print("--- Verification Report ---")
    
    # Check if usertable has student_oids
    user = await db.usertable.find_one({"student_oids": {"$exists": True, "$ne": []}})
    if user:
        print(f"✅ usertable has ObjectID links. Found: {user.get('student_oids')}")
    else:
        print("❌ usertable missing ObjectID links.")

    # Check if evaluations has student_oid
    ev = await db.evaluations.find_one({"student_oid": {"$exists": True}})
    if ev:
        print(f"✅ evaluations has ObjectID link. Found: {ev.get('student_oid')}")
    else:
        print("❌ evaluations missing ObjectID link.")

    # Check if notifications has student_oid
    notif = await db.notifications.find_one({"student_oid": {"$exists": True}})
    if notif:
        print(f"✅ notifications has ObjectID link. Found: {notif.get('student_oid')}")
    else:
        print("❌ notifications missing ObjectID link.")

if __name__ == "__main__":
    asyncio.run(verify_migration())
