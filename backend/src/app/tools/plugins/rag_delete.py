import json
import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")


class RagDeleteArgs(BaseModel):
    s3_url: str = Field(..., description="Original s3:// URL of the document to delete (visible in rag_list output as 'ID:')")


class RagDeletePlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "rag_delete"

    @property
    def description(self) -> str:
        return (
            "Delete a document from the RAG index and remove it from S3. "
            "Use the original s3:// URL shown as 'ID:' in rag_list output. "
            "Documents currently being processed cannot be deleted."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return RagDeleteArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        s3_url: str = kwargs["s3_url"]
        transport = StreamableHttpTransport(url=f"{_RAG_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool("rag_delete", {"s3_url": s3_url})
            if not result.content:
                return "Delete returned no response."
            payload = json.loads(result.content[-1].text)
        except Exception as e:
            return f"Error deleting document: {e}"

        if payload.get("error"):
            return f"Delete failed: {payload['error']}"

        msg = (
            f"Deleted '{payload['filename']}' — {payload['chunks_removed']} chunk(s) removed from index."
        )
        if payload.get("s3_warning"):
            msg += f"\nWarning: {payload['s3_warning']}"
        return msg
