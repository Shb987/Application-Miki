import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.settings import settings

async def run():
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.DB_NAME]
    
    docs = await db.textbook.find({"standard": "8"}).to_list(None)
    subjects = list(set([d.get("subject") for d in docs]))
    print("Subjects in standard 8:", subjects)
    
    docs = await db.textbook.find({"standard": "10"}).to_list(None)
    subjects = list(set([d.get("subject") for d in docs]))
    print("Subjects in standard 10:", subjects)

asyncio.run(run())
