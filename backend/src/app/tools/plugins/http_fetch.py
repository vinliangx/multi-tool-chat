import httpx
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin


class HttpFetchArgs(BaseModel):
    url: str = Field(..., description="Absolute http(s) URL to fetch")
    method: str = Field("GET", description="HTTP method")
    max_bytes: int = Field(2_000_000, description="Truncate response above this size")


class HttpFetchPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "http_fetch"

    @property
    def description(self) -> str:
        return "Fetch a URL over HTTP(S) and return the body. Use for web pages, JSON APIs, etc. (Up to 2MB)"

    @property
    def args_schema(self) -> type[BaseModel]:
        return HttpFetchArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        url = kwargs["url"]
        method = kwargs.get("method", "GET")
        max_bytes = kwargs.get("max_bytes", 2_000_000)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.request(method, url)
        text = resp.text
        if len(text.encode("utf-8")) > max_bytes:
            text = text[:max_bytes] + "\n... [truncated]"
        return f"HTTP {resp.status_code} {url}\n\n{text}"
