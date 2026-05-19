import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://localhost:8004")


class ListConflictsArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")


class ListConflictsPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.list_conflicts"

    @property
    def description(self) -> str:
        return (
            "List all pending duplicate-transaction conflicts for the user. "
            "Each conflict shows the existing entry and the incoming entry that was blocked. "
            "To resolve: call add_income or add_expense with force=true to keep both entries, "
            "or simply discard the incoming entry by doing nothing."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return ListConflictsArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_FINANCE_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool("list_conflicts", kwargs)
            if not result.content:
                return "Error: Finance service returned empty response"
            return result.content[-1].text
        except Exception as e:
            return f"Error calling finance service: {e}"
