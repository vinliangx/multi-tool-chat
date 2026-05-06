"""Recall tool — the agent's explicit way to bring a stored result back."""

from __future__ import annotations

import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.session.manager import recall_payload


class RecallArgs(BaseModel):
    handle: str = Field(
        ...,
        description="The handle returned by an earlier tool call (e.g. 'tr_abc123').",
    )


def factory(_session_id_provider):
    async def _coro(handle: str) -> str:
        payload, rec = await recall_payload(handle)
        if rec is None:
            return f"unknown handle: {handle}"
        head = (
            f"recalled tool={rec.tool_name} args={rec.tool_args} "
            f"size={rec.payload_size_bytes}B tokens~{rec.token_estimate}\n\n"
        )
        return head + (payload or "")

    return StructuredTool.from_function(
        coroutine=_coro,
        name="recall",
        description=(
            "Bring the full payload of a previously stored tool result back into context. "
            "Use this when the summary you have is not enough and you need raw detail. "
            "Pass the 'handle' you received from the earlier tool call."
        ),
        args_schema=RecallArgs,
    )
