from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from app.tools.base import make_session_tool


class HttpFetchArgs(BaseModel):
    url: str = Field(..., description="Absolute http(s) URL to fetch")
    method: str = Field("GET", description="HTTP method")
    max_bytes: int = Field(2_000_000, description="Truncate response above this size")


async def _run(url: str, method: str = "GET", max_bytes: int = 2_000_000) -> str:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.request(method, url)
    text = resp.text
    if len(text.encode("utf-8")) > max_bytes:
        text = text[:max_bytes] + "\n... [truncated]"
    return f"HTTP {resp.status_code} {url}\n\n{text}"


def factory(session_id_provider):
    return make_session_tool(
        name="http_fetch",
        description="Fetch a URL over HTTP(S) and return the body. Use for web pages, JSON APIs, etc. (Up to 2MB)",
        args_schema=HttpFetchArgs,
        runner=_run,
        session_id_provider=session_id_provider,
    )
