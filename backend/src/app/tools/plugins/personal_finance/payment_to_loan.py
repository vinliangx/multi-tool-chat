import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://localhost:8004")


class PaymentToLoanArgs(BaseModel):
    loan_name: str = Field(..., description="Loan label, e.g. 'Car loan'")
    amount: float = Field(..., gt=0, description="Payment amount in dollars")


class PaymentToLoanPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.payment_to_loan"

    @property
    def description(self) -> str:
        return (
            "Record a payment toward a loan balance. "
            "Reduces the loan's remaining balance by the payment amount."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return PaymentToLoanArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_FINANCE_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool(
                    "payment_to_loan", {"user_id": context.user_id, **kwargs}
                )
            if not result.content:
                return "Error: Finance service returned empty response"
            return result.content[-1].text
        except Exception as e:
            return f"Error calling finance service: {e}"
