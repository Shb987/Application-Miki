from motor.motor_asyncio import AsyncIOMotorClient
from app.core.settings import settings
from bson import ObjectId
import fastapi.encoders

# Globally configure FastAPI's jsonable_encoder to encode bson.ObjectId as str
fastapi.encoders.ENCODERS_BY_TYPE[ObjectId] = str

client = AsyncIOMotorClient(settings.MONGO_URI)
db = client[settings.DB_NAME]
