import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def create_production_indexes():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "New_app")
    
    print(f"Connecting to: {mongo_uri}")
    print(f"Database: {db_name}")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    # Define indexes to create
    # Format: (collection, field, unique_flag, index_name)
    index_tasks = [
        ("students", "mobile_number", False), # Not unique as one mobile might have multiple students
        ("usertable", "mobile_number", True),
        ("usertable", "student_ids", False),
        ("evaluations", "student_id", False),
        ("evaluations", "evaluation_id", True),
        ("otps", "mobile_number", True),
        ("notifications", "student_id", False),
        ("answers", "student_id", False),
        ("career_analyzer", "student_id", False),
        ("quiz_submissions", "student_id", False)
    ]
    
    for coll_name, field, is_unique in index_tasks:
        try:
            print(f"Creating index for {coll_name}({field})...", end=" ")
            await db[coll_name].create_index(field, unique=is_unique)
            print("✅ Done")
        except Exception as e:
            print(f"❌ Failed: {e}")

    # Special case: TTL index for OTPs (autodelete after 'expiry' field time)
    try:
        print("Creating TTL index for otps(expiry)...", end=" ")
        await db.otps.create_index("expiry", expireAfterSeconds=0)
        print("✅ Done")
    except Exception as e:
         print(f"❌ Failed: {e}")

    print("\nAll production indexes have been processed.")

if __name__ == "__main__":
    asyncio.run(create_production_indexes())
