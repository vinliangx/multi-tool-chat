import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://localhost:8004")


class AddLoanArgs(BaseModel):
    loan_name: str = Field(..., description="Loan label, e.g. 'Car loan'")
    original_amount: float = Field(..., description="Total amount originally borrowed")
    balance: float = Field(..., description="Remaining amount owed")
    apr: float = Field(..., description="Annual percentage rate, e.g. 6.5 for 6.5%")
    monthly_payment: float = Field(..., description="Fixed monthly payment amount")
    due_date: int = Field(..., ge=1, le=31, description="Day of month payment is due")
    start_date: str = Field(
        ..., description="Loan origination date in YYYY-MM-DD format"
    )


class AddLoanPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.add_loan"

    @property
    def description(self) -> str:
        return (
            "Add or update a loan account. If a loan with the same name already "
            "exists for the user it is updated in place."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return AddLoanArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_FINANCE_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool(
                    "add_loan", {"user_id": context.user_id, **kwargs}
                )
            if not result.content:
                return "Error: Finance service returned empty response"
            return result.content[-1].text
        except Exception as e:
            return f"Error calling finance service: {e}"
