from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

# Connection values come from the centralized settings object, which loads
# .env on import. This keeps a single source of truth for configuration.
client = AsyncIOMotorClient(settings.MONGODB_URL)

database = client[settings.DATABASE_NAME]
