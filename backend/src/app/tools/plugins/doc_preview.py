import json
import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8003")


class DocPreviewArgs(BaseModel):
    s3_url: str = Field(
        ...,
        description=(
            "S3 URL of the document or image to preview (s3://bucket/key). "
            "Supports txt, pdf, docx, pptx, xlsx, and images."
        ),
    )


class DocPreviewPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "doc_preview"

    @property
    def description(self) -> str:
        return (
            "Preview a document or image from S3 without indexing it. "
            "Returns a raw text snippet and an LLM-generated summary."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return DocPreviewArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_RAG_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool("doc_preview", {"s3_url": kwargs["s3_url"]})
            if not result.content:
                return "Error: RAG service returned empty response"
            data = json.loads(result.content[-1].text)
        except Exception as e:
            return f"Error previewing document: {e}"
        if "error" in data:
            return f"Error: {data['error']}"
        return (
            f"File: {data['filename']} ({data['content_type']})\n\n"
            f"Snippet:\n{data['snippet']}\n\n"
            f"Summary:\n{data['summary']}"
        )
