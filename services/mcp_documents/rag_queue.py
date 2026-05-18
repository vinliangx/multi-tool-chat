from __future__ import annotations

import uuid

import redis.asyncio as aioredis

from config import settings

_client: aioredis.Redis | None = None
QUEUE_KEY = "rag:queue"


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def enqueue(doc_id: uuid.UUID) -> None:
    await get_redis().rpush(QUEUE_KEY, str(doc_id))


async def dequeue_timeout(timeout: int = 5) -> str | None:
    result = await get_redis().blpop(QUEUE_KEY, timeout=timeout)
    if result:
        _, job_id = result
        return job_id
    return None


async def requeue_interrupted(doc_ids: list[str]) -> None:
    if not doc_ids:
        return
    r = get_redis()
    existing = set(await r.lrange(QUEUE_KEY, 0, -1))
    for doc_id in doc_ids:
        if doc_id not in existing:
            await r.rpush(QUEUE_KEY, doc_id)


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None
