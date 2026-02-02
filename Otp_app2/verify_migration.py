
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
DB_NAME = os.getenv("DB_NAME", "new_app2")

async def verify():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    q = await db.quiz_questions.find_one({})
    if q:
        print(f"Question: {q.get('question_text')[:50]}")
        print(f"Correct Answer: {q.get('correct_answer')}")
        print(f"Type: {type(q.get('correct_answer'))}")
    else:
        print("No questions found")
    client.close()

if __name__ == "__main__":
    asyncio.run(verify())
