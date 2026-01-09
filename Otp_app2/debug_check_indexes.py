import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def check_indexes():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "New_app")
    
    print(f"Connecting to: {mongo_uri}")
    print(f"Database: {db_name}\n")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    collections = ["students", "usertable", "evaluations", "otps", "notifications"]
    
    for coll_name in collections:
        print(f"--- Indexes for collection: {coll_name} ---")
        try:
            indexes = await db[coll_name].list_indexes().to_list(None)
            for idx in indexes:
                print(f" - {idx['name']}: {idx['key']}")
        except Exception as e:
            print(f" Error checking {coll_name}: {e}")
        print()

if __name__ == "__main__":
    asyncio.run(check_indexes())
