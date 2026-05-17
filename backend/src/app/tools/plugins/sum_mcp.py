import os

import httpx
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_SUM_SERVICE_URL = os.getenv("SUM_SERVICE_URL", "http://localhost:8001")


class SumArgs(BaseModel):
    a: float = Field(..., description="First number")
    b: float = Field(..., description="Second number")


class SumMcpPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "mcp_sum"

    @property
    def description(self) -> str:
        return "Sum two numbers via the remote MCP sum microservice."

    @property
    def args_schema(self) -> type[BaseModel]:
        return SumArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_SUM_SERVICE_URL}/sum",
                json={"a": kwargs["a"], "b": kwargs["b"]},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["expression"]
