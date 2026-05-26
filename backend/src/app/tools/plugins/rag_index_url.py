import json
import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")


class RagIndexUrlArgs(BaseModel):
    url: str = Field(..., description="The URL of the webpage to fetch and index for RAG search.")


class RagIndexUrlPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "rag_index_url"

    @property
    def description(self) -> str:
        return "Fetch a webpage, extract its text, and queue it for RAG indexing. Returns job_id and queue position."

    @property
    def args_schema(self) -> type[BaseModel]:
        return RagIndexUrlArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_RAG_SERVICE_URL}/mcp")
        url = kwargs["url"]
        try:
            async with Client(transport) as client:
                result = await client.call_tool("rag_index_url", {"url": url})
            if not result.content:
                return "Error: RAG service returned empty response"
            data = json.loads(result.content[-1].text)
        except Exception as e:
            return f"Error indexing URL: {e}"
        if "error" in data:
            return f"Error: {data['error']}"
        return (
            f"Webpage queued for indexing.\n"
            f"Job ID: {data['job_id']}\n"
            f"URL: {data['url']}\n"
            f"Position in queue: {data['position_in_queue']}"
        )
