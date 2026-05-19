import json
import os
from typing import Optional

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")


class RagListArgs(BaseModel):
    search_term: Optional[str] = Field(None, description="Filter documents by filename (case-insensitive partial match)")
    max_documents: int = Field(20, description="Maximum number of documents to return (default 20)")


class RagListPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "rag_list"

    @property
    def description(self) -> str:
        return "List documents in the RAG index with their status, chunk count, dates, and temporary S3 download links. Optionally filter by filename."

    @property
    def args_schema(self) -> type[BaseModel]:
        return RagListArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_RAG_SERVICE_URL}/mcp")
        params: dict = {"max_documents": kwargs.get("max_documents", 20)}
        if kwargs.get("search_term"):
            params["search_term"] = kwargs["search_term"]
        try:
            async with Client(transport) as client:
                result = await client.call_tool("rag_list", params)
            if not result.content:
                return "No documents found."
            payload = json.loads(result.content[-1].text)
        except Exception as e:
            return f"Error listing documents: {e}"
        docs = payload.get("documents", [])
        has_more = payload.get("has_more", False)
        if not docs:
            return "No documents have been uploaded yet."
        lines = [f"Found {payload['count']} document(s):"]
        for i, d in enumerate(docs, 1):
            completed = d["completed_at"] or "—"
            chunks = d["chunk_count"] if d["chunk_count"] is not None else "—"
            error = f" | Error: {d['error']}" if d["error"] else ""
            lines.append(
                f"\n[{i}] {d['filename']} | Status: {d['status']} | Chunks: {chunks}{error}\n"
                f"    Uploaded: {d['created_at']} | Completed: {completed}\n"
                f"    ID: {d['original_s3_url']}\n"
                f"    Link: {d['s3_url']}"
            )
        if has_more:
            lines.append("\n... there are more documents. Use search_term to narrow results or increase max_documents.")
        return "\n".join(lines)
