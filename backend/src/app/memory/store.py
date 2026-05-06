import redis.asyncio as redis
from app.config import settings


class MemoryStore:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.redis = redis.from_url(settings.redis_url)
