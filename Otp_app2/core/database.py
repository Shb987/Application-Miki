from motor.motor_asyncio import AsyncIOMotorClient
from core.settings import settings

client = AsyncIOMotorClient(settings.MONGO_URI)
db = client[settings.DB_NAME]
