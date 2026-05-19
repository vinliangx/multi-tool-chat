import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://localhost:8004")


class AddCreditCardArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")
    cc_name: str = Field(..., description="Card name / issuer, e.g. 'Chase Sapphire'")
    credit_limit: float = Field(..., description="Maximum credit limit in dollars")
    apr: float = Field(..., description="Annual percentage rate, e.g. 24.99 for 24.99%")
    min_payment: float = Field(
        ..., description="Required minimum payment per billing cycle"
    )
    cut_date: int = Field(
        ..., ge=1, le=31, description="Day of month the billing cycle closes"
    )
    due_date: int = Field(..., ge=1, le=31, description="Day of month payment is due")
    balance: float = Field(0.0, description="Current outstanding balance")


class AddCreditCardPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.add_credit_card"

    @property
    def description(self) -> str:
        return (
            "Add or update a credit card account. If a card with the same name already "
            "exists for the user it is updated in place."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return AddCreditCardArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_FINANCE_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool("add_credit_card", kwargs)
            if not result.content:
                return "Error: Finance service returned empty response"
            return result.content[-1].text
        except Exception as e:
            return f"Error calling finance service: {e}"
