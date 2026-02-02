
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
    with open("migration_result.txt", "w") as f:
        if q:
            f.write(f"Question: {q.get('question_text')[:50]}\n")
            f.write(f"Correct Answer: {q.get('correct_answer')}\n")
            f.write(f"Type: {type(q.get('correct_answer'))}\n")
        else:
            f.write("No questions found\n")
    client.close()

if __name__ == "__main__":
    asyncio.run(verify())
