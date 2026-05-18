import json
import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel

from app.tools.plugin import ToolContext, ToolPlugin

_RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")


class RagStatusArgs(BaseModel):
    pass


class RagStatusPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "rag_queue_status"

    @property
    def description(self) -> str:
        return "Get the RAG indexing queue: ordered list of documents pending or currently being processed."

    @property
    def args_schema(self) -> type[BaseModel]:
        return RagStatusArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_RAG_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool("rag_queue_status", {})
            if not result.content:
                return "Queue is empty."
            rows = json.loads(result.content[-1].text)
        except Exception as e:
            return f"Error fetching queue status: {e}"
        if not rows:
            return "Queue is empty — no documents pending."
        lines = [f"{len(rows)} document(s) in queue:"]
        for i, r in enumerate(rows, 1):
            name = r.get("filename") or r["s3_url"]
            lines.append(
                f"  {i}. [{r['status'].upper()}] {name}"
                f" (job: {r['job_id']}, queued: {r['created_at']})"
            )
        return "\n".join(lines)
