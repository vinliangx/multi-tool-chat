import os

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from pydantic import BaseModel

from app.tools.plugin import ToolContext, ToolPlugin

_FINANCE_SERVICE_URL = os.getenv("FINANCE_SERVICE_URL", "http://localhost:8004")


class GetReportArgs(BaseModel):
    pass


class GetReportPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.get_report"

    @property
    def description(self) -> str:
        return (
            "Generate a financial summary for the current calendar month: "
            "burn rate (% of income spent) and daily budget (remaining income / remaining days). "
            "Recurring income from prior months is projected forward when no explicit entry exists."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return GetReportArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        transport = StreamableHttpTransport(url=f"{_FINANCE_SERVICE_URL}/mcp")
        try:
            async with Client(transport) as client:
                result = await client.call_tool(
                    "get_report", {"user_id": context.user_id}
                )
            if not result.content:
                return "Error: Finance service returned empty response"
            return result.content[-1].text
        except Exception as e:
            return f"Error calling finance service: {e}"
