import os
from typing import Literal

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://localhost:8004")

CATEGORIES = Literal[
    "Housing",
    "Food & Groceries",
    "Transport",
    "Utilities",
    "Health",
    "Entertainment",
    "Debt Payment",
    "Other",
]


class AddExpenseArgs(BaseModel):
    amount: float = Field(..., description="Expense amount in dollars")
    description: str = Field(..., description="Short label for the expense")
    date: str = Field(..., description="Date of the expense in YYYY-MM-DD format")
    category: CATEGORIES = Field(..., description="Expense category")
    force: bool = Field(
        False,
        description="Set to true to proceed with insertion even if a duplicate is detected",
    )


class AddExpensePlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.add_expense"

    @property
    def description(self) -> str:
        return (
            "Record an expense. Checks for duplicates "
            "(same user, amount, date, description — case-insensitive) before inserting. "
            "Set force=true to override a detected duplicate."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return AddExpenseArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_FINANCE_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool(
                    "add_expense", {"user_id": context.user_id, **kwargs}
                )
            if not result.content:
                return "Error: Finance service returned empty response"
            return result.content[-1].text
        except Exception as e:
            return f"Error calling finance service: {e}"
