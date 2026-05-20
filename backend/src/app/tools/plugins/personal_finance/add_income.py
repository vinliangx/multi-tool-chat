import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://localhost:8004")


class AddIncomeArgs(BaseModel):
    amount: float = Field(..., description="Income amount in dollars")
    source: str = Field(..., description="Source label, e.g. 'Salary', 'Freelance'")
    month: int = Field(
        ..., ge=1, le=12, description="Month the income applies to (1-12)"
    )
    year: int = Field(..., ge=2000, description="Year the income applies to")
    recurring: bool = Field(
        False, description="If true, auto-projects into subsequent months"
    )
    force: bool = Field(
        False,
        description="Set to true to proceed with insertion even if a duplicate is detected",
    )


class AddIncomePlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.add_income"

    @property
    def description(self) -> str:
        return (
            "Record an income entry for a given month. Checks for duplicates "
            "(same user, amount, source, month, year) before inserting. "
            "Set force=true to override a detected duplicate."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return AddIncomeArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_FINANCE_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool(
                    "add_income", {"user_id": context.user_id, **kwargs}
                )
            if not result.content:
                return "Error: Finance service returned empty response"
            return result.content[-1].text
        except Exception as e:
            return f"Error calling finance service: {e}"
