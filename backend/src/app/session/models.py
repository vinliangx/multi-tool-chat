from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolResultRecord(BaseModel):
    """Metadata + payload pointer for a single tool invocation in a session.

    The agent receives the metadata + summary on first invocation, and may
    later call `recall(handle)` to pull the full payload back into context.
    """

    handle: str
    session_id: str
    tool_name: str
    tool_args: dict[str, Any]
    summary: str
    token_estimate: int
    payload_size_bytes: int
    payload_location: str
    inline_payload: str | None = None
    created_at: str = Field(default_factory=_now)

    def agent_view(self) -> dict[str, Any]:
        view: dict[str, Any] = {
            "handle": self.handle,
            "tool": self.tool_name,
            "summary": self.summary,
            "token_estimate": self.token_estimate,
            "size_bytes": self.payload_size_bytes,
            "created_at": self.created_at,
        }
        if self.inline_payload is not None:
            view["result"] = self.inline_payload
        return view


class SessionRecord(BaseModel):
    session_id: str
    title: str
    user_id: str = ""
    created_at: str = Field(default_factory=_now)
