from __future__ import annotations

import json
import uuid
from typing import Protocol

import redis.asyncio as redis

from app.config import settings
from app.session.models import SessionRecord, ToolResultRecord


class SessionStore(Protocol):
    async def create_session(self, session_id: str, title: str, user_id: str = "") -> SessionRecord: ...

    async def ensure_session(self, session_id: str, title: str, user_id: str = "") -> SessionRecord: ...

    async def delete_session(self, session_id: str) -> None: ...

    async def get_session(self, session_id: str) -> SessionRecord | None: ...

    async def put_result(self, record: ToolResultRecord, payload: str) -> None: ...

    async def get_payload(self, handle: str) -> str | None: ...

    async def get_record(self, handle: str) -> ToolResultRecord | None: ...

    async def list_records(self, session_id: str) -> list[ToolResultRecord]: ...

    async def list_sessions(self, user_id: str = "") -> list[SessionRecord]: ...


class RedisSessionStore:
    """Redis-backed store using JSON for serialization."""

    def __init__(self) -> None:
        self._redis = redis.from_url(settings.redis_url)
        self._result_pattern = "result:*"

    async def create_session(self, session_id: str, title: str, user_id: str = "") -> SessionRecord:
        rec = SessionRecord(session_id=session_id, title=title, user_id=user_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset("session", session_id, rec.model_dump_json())
            if user_id:
                pipe.sadd(f"user:{user_id}:sessions", session_id)
            await pipe.execute()
        return rec

    async def ensure_session(self, session_id: str, title: str, user_id: str = "") -> SessionRecord:
        exists = await self._redis.hexists("session", session_id)
        if not exists:
            return await self.create_session(session_id, title, user_id)
        data = await self._redis.hget("session", session_id)
        return SessionRecord.model_validate_json(data)

    async def delete_session(self, session_id: str) -> None:
        data = await self._redis.hget("session", session_id)
        user_id = ""
        if data:
            rec = SessionRecord.model_validate_json(data)
            user_id = rec.user_id

        handles = await self._redis.smembers(f"records:{session_id}")
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hdel("session", session_id)
            pipe.delete(f"records:{session_id}")
            if user_id:
                pipe.srem(f"user:{user_id}:sessions", session_id)
            if handles:
                decoded = [h.decode() if isinstance(h, bytes) else h for h in handles]
                pipe.hdel("handles", *decoded)
                for h in decoded:
                    pipe.delete(f"payload:{h}")
            await pipe.execute()

    async def get_session(self, session_id: str) -> SessionRecord | None:
        data = await self._redis.hget("session", session_id)
        return SessionRecord.model_validate_json(data) if data else None

    async def put_result(self, record: ToolResultRecord, payload: str) -> None:
        record_dict = record.model_dump()
        await self._redis.hset("handles", record.handle, json.dumps(record_dict))
        payload_key = f"payload:{record.handle}"
        await self._redis.set(payload_key, payload)
        await self._redis.sadd(f"records:{record.session_id}", record.handle)

    async def get_payload(self, handle: str) -> str | None:
        payload = await self._redis.get(f"payload:{handle}")
        return payload.decode() if payload else None

    async def get_record(self, handle: str) -> ToolResultRecord | None:
        data = await self._redis.hget("handles", handle)
        return ToolResultRecord.model_validate_json(data) if data else None

    async def list_records(self, session_id: str) -> list[ToolResultRecord]:
        handles = await self._redis.smembers(f"records:{session_id}")
        records = []
        for handle in handles:
            rec = await self.get_record(handle)
            if rec:
                records.append(rec)
        return records

    async def list_sessions(self, user_id: str = "") -> list[SessionRecord]:
        if user_id:
            session_ids = await self._redis.smembers(f"user:{user_id}:sessions")
            sessions = []
            for sid in session_ids:
                sid_str = sid.decode() if isinstance(sid, bytes) else sid
                data = await self._redis.hget("session", sid_str)
                if data:
                    sessions.append(SessionRecord.model_validate_json(data))
            return sessions
        # No user_id — return all (admin / backward-compat path)
        session_ids = await self._redis.hkeys("session")
        sessions = []
        for session_id in session_ids:
            data = await self._redis.hget("session", session_id)
            if data:
                sessions.append(SessionRecord.model_validate_json(data))
        return sessions


class InMemoryStore:
    """In-memory store for testing."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._records: dict[str, ToolResultRecord] = {}
        self._payloads: dict[str, str] = {}
        self._session_handles: dict[str, set[str]] = {}

    async def create_session(self, session_id: str, title: str, user_id: str = "") -> SessionRecord:
        rec = SessionRecord(session_id=session_id, title=title, user_id=user_id)
        self._sessions[session_id] = rec
        return rec

    async def ensure_session(self, session_id: str, title: str, user_id: str = "") -> SessionRecord:
        if session_id in self._sessions:
            return self._sessions[session_id]
        return await self.create_session(session_id, title, user_id)

    async def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        for handle in self._session_handles.pop(session_id, set()):
            self._records.pop(handle, None)
            self._payloads.pop(handle, None)

    async def get_session(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)

    async def put_result(self, record: ToolResultRecord, payload: str) -> None:
        self._records[record.handle] = record
        self._payloads[record.handle] = payload
        self._session_handles.setdefault(record.session_id, set()).add(record.handle)

    async def get_payload(self, handle: str) -> str | None:
        return self._payloads.get(handle)

    async def get_record(self, handle: str) -> ToolResultRecord | None:
        return self._records.get(handle)

    async def list_records(self, session_id: str) -> list[ToolResultRecord]:
        return [self._records[h] for h in self._session_handles.get(session_id, set())]

    async def list_sessions(self, user_id: str = "") -> list[SessionRecord]:
        if user_id:
            return [s for s in self._sessions.values() if s.user_id == user_id]
        return list(self._sessions.values())


_store: SessionStore | None = None


def get_store() -> SessionStore:
    global _store
    if _store is None:
        _store = RedisSessionStore()
    return _store


def new_handle() -> str:
    return f"tr_{uuid.uuid4().hex[:12]}"
