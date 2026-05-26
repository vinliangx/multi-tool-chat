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
        return "Get RAG indexing status: pending/processing queue plus completed and failed documents indexed this session."

    @property
    def args_schema(self) -> type[BaseModel]:
        return RagStatusArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_RAG_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool("rag_queue_status", {})
            if not result.content:
                return "No status available."
            payload = json.loads(result.content[-1].text)
        except Exception as e:
            return f"Error fetching queue status: {e}"

        docs = payload.get("documents", [])
        session_start = payload.get("session_start", "unknown")

        if not docs:
            return f"No documents in queue or indexed this session (since {session_start})."

        by_status: dict[str, list] = {"pending": [], "processing": [], "completed": [], "failed": []}
        for r in docs:
            by_status.setdefault(r["status"], []).append(r)

        lines = [f"RAG status (session since {session_start}):"]

        active = by_status["processing"] + by_status["pending"]
        if active:
            lines.append(f"\n  In queue ({len(active)}):")
            for r in active:
                name = r.get("filename") or r["s3_url"]
                lines.append(f"    [{r['status'].upper()}] {name} (job: {r['job_id']}, queued: {r['created_at']})")

        if by_status["completed"]:
            lines.append(f"\n  Completed ({len(by_status['completed'])}):")
            for r in by_status["completed"]:
                name = r.get("filename") or r["s3_url"]
                chunks = r.get("chunk_count") or 0
                lines.append(f"    {name} — {chunks} chunk(s), done: {r.get('completed_at') or 'unknown'}")

        if by_status["failed"]:
            lines.append(f"\n  Failed ({len(by_status['failed'])}):")
            for r in by_status["failed"]:
                name = r.get("filename") or r["s3_url"]
                lines.append(f"    {name} — {r.get('error') or 'no error details'}")

        return "\n".join(lines)
