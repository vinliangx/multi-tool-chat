import json
import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")


class RagSearchArgs(BaseModel):
    query: str = Field(..., description="Text to search for across indexed documents")
    top_k: int = Field(5, description="Number of top results to return (default 5)")


class RagSearchPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "Semantic search over RAG-indexed documents. Returns ranked text chunks with temporary S3 download links."

    @property
    def args_schema(self) -> type[BaseModel]:
        return RagSearchArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_RAG_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool(
                    "rag_search",
                    {"query": kwargs["query"], "top_k": kwargs.get("top_k", 5)},
                )
            if not result.content:
                return "No results found"
            results = json.loads(result.content[-1].text)
        except Exception as e:
            return f"Error searching documents: {e}"
        if not results:
            return "No matching documents found."
        lines = [f"Found {len(results)} result(s):"]
        for i, r in enumerate(results, 1):
            snippet = r["content"][:500]
            if len(r["content"]) > 500:
                snippet += "..."
            lines.append(
                f"\n[{i}] Score: {r['score']:.3f} | File: {r['filename']}\n"
                f"{snippet}\n"
                f"Link: {r['s3_url']}"
            )
        return "\n".join(lines)
