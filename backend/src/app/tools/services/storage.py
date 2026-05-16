"""StorageService — wraps the underlying SessionStore for tool access."""

from __future__ import annotations

from app.session.models import SessionRecord, ToolResultRecord
from app.session.store import get_store


class StorageService:
    async def put_result(self, record: ToolResultRecord, payload: str) -> None:
        await get_store().put_result(record, payload)

    async def get_payload(self, handle: str) -> str | None:
        return await get_store().get_payload(handle)

    async def get_record(self, handle: str) -> ToolResultRecord | None:
        return await get_store().get_record(handle)

    async def put_session(self, session_id: str, title: str) -> SessionRecord:
        return await get_store().create_session(session_id, title)

    async def ensure_session(self, session_id: str, title: str) -> SessionRecord:
        return await get_store().ensure_session(session_id, title)

    async def list_sessions(self) -> list[SessionRecord]:
        return await get_store().list_sessions()

    async def delete_session(self, session_id: str) -> None:
        await get_store().delete_session(session_id)
