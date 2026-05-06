"""Session Manager — the bridge between tool execution and the agent.

`record_tool_result` is what every tool calls after producing output.
Small results are kept inline; large ones get summarized via the
sub-agent and persisted, with only metadata + summary returned to the
agent. The agent uses `recall(handle)` to pull a full payload back.
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


async def record_tool_result(
    session_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    payload: str,
) -> dict[str, Any]:
    """Persist a tool result and return what the agent should see now.

    Decision tree:
      - tokens <= inline_limit: return full payload inline + store it.
      - tokens <= summarize_limit: summarize via sub-agent, return summary.
      - otherwise: chunk-summarize and return summary only.
    """
    from app.agent.summarizer import summarize  # local import to avoid cycle

    handle = new_handle()
    token_count = _tokens(payload)
    payload_bytes = len(payload.encode("utf-8"))
    location = f"sessions/{session_id}/results/{handle}.txt"

    inline: str | None = None
    if token_count <= settings.tool_result_inline_token_limit:
        inline = payload
        summary = _short_preview(payload)
    else:
        summary = await summarize(
            payload,
            tool_name=tool_name,
            tool_args=tool_args,
            target_tokens=400,
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


def _short_preview(payload: str, max_chars: int = 240) -> str:
    flat = " ".join(payload.split())
    return flat if len(flat) <= max_chars else flat[: max_chars - 1] + "…"


async def recall_payload(handle: str) -> tuple[str | None, ToolResultRecord | None]:
    store = get_store()
    rec = await store.get_record(handle)
    if rec is None:
        return None, None
    payload = await store.get_payload(handle)
    return payload, rec
