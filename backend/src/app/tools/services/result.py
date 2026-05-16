"""ResultProcessor — applies the truncation/summarization policy to tool outputs.

Replaces the old `record_tool_result` in `session/manager.py`.
"""

from __future__ import annotations

from typing import Any

import tiktoken

from app.config import settings
from app.session.models import ToolResultRecord
from app.session.store import get_store, new_handle

_enc = tiktoken.get_encoding("cl100k_base")


def _tokens(text: str) -> int:
    return len(_enc.encode(text))


def _short_preview(payload: str, max_chars: int = 240) -> str:
    flat = " ".join(payload.split())
    return flat if len(flat) <= max_chars else flat[: max_chars - 1] + "…"


class ResultProcessor:
    async def process(
        self,
        session_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        payload: str,
        *,
        inline_limit: int | None = None,
        summarize_limit: int | None = None,
    ) -> dict[str, Any]:
        from app.agent.summarizer import summarize

        inline_limit = inline_limit or settings.tool_result_inline_token_limit
        summarize_limit = summarize_limit or settings.tool_result_summarize_token_limit

        handle = new_handle()
        token_count = _tokens(payload)
        payload_bytes = len(payload.encode("utf-8"))
        location = f"sessions/{session_id}/results/{handle}.txt"

        inline: str | None = None
        if token_count <= inline_limit:
            inline = payload
            summary = _short_preview(payload)
        else:
            summary = await summarize(
                payload,
                tool_name=tool_name,
                tool_args=tool_args,
                target_tokens=512,
            )

        record = ToolResultRecord(
            handle=handle,
            session_id=session_id,
            tool_name=tool_name,
            tool_args=tool_args,
            summary=summary,
            token_estimate=token_count,
            payload_size_bytes=payload_bytes,
            payload_location=location,
            inline_payload=inline,
        )
        await get_store().put_result(record, payload)
        return record.agent_view()

    async def recall(self, handle: str) -> tuple[str | None, ToolResultRecord | None]:
        store = get_store()
        rec = await store.get_record(handle)
        if rec is None:
            return None, None
        payload = await store.get_payload(handle)
        return payload, rec
