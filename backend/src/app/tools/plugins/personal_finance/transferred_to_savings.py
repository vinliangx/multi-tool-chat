import os
from datetime import date

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://localhost:8004")


class TransferredToSavingsArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")
    amount: float = Field(
        ..., gt=0, description="Amount transferred to savings in dollars"
    )
    date: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="Transfer date in YYYY-MM-DD format (defaults to today)",
    )
    note: str | None = Field(None, description="Optional label, e.g. 'Emergency fund'")


class TransferredToSavingsPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.transferred_to_savings"

    @property
    def description(self) -> str:
        return (
            "Record money transferred to savings. "
            "Tracked independently — does not affect any credit card or loan balance."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return TransferredToSavingsArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_FINANCE_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool("transferred_to_savings", kwargs)
            if not result.content:
                return "Error: Finance service returned empty response"
            return result.content[-1].text
        except Exception as e:
            return f"Error calling finance service: {e}"
