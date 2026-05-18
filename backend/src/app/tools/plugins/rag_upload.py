import json
import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")


class RagUploadArgs(BaseModel):
    s3_url: str = Field(..., description="S3 URL of the document to index (s3://bucket/key). Supports txt, pdf, docx, pptx, xlsx, and images.")


class RagUploadPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "rag_upload"

    @property
    def description(self) -> str:
        return "Queue an S3 document for chunking and RAG indexing. Returns job_id and queue position."

    @property
    def args_schema(self) -> type[BaseModel]:
        return RagUploadArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_RAG_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool("rag_upload", {"s3_url": kwargs["s3_url"]})
            if not result.content:
                return "Error: RAG service returned empty response"
            data = json.loads(result.content[-1].text)
        except Exception as e:
            return f"Error queuing document: {e}"
        if "error" in data:
            return f"Error: {data['error']}"
        return (
            f"Document queued for indexing.\n"
            f"Job ID: {data['job_id']}\n"
            f"Filename: {data['filename']}\n"
            f"Position in queue: {data['position_in_queue']}"
        )
