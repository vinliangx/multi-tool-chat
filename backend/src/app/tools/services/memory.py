"""MemoryService — wraps the MemoryStore singleton for tool access."""

from __future__ import annotations

from app.memory.store import MemoryStore


class MemoryService:
    async def get_user_memory(self, user_id: str) -> dict | None:
        raw = await MemoryStore().redis.get(f"users:{user_id}")
        if raw is None:
            return None
        import json

        return json.loads(raw.decode())

    async def save_user_memory(self, user_id: str, data: dict) -> None:
        import json

        await MemoryStore().redis.set(
            f"users:{user_id}",
            json.dumps(data),
        )
