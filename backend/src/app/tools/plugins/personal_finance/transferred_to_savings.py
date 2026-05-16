from datetime import date

from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin
from app.tools.plugins.personal_finance.db import get_pool


class TransferredToSavingsArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")
    amount: float = Field(..., gt=0, description="Amount transferred to savings in dollars")
    date: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="Transfer date in YYYY-MM-DD format (defaults to today)",
    )
    note: str | None = Field(None, description="Optional label, e.g. 'Emergency fund'")


class TransferredToSavingsPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "transferred_to_savings"

    @property
    def description(self) -> str:
        return (
            "Record money transferred to savings. "
            "Tracked independently — does not affect any credit card or loan balance."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return TransferredToSavingsArgs

    async def on_init(self, kernel) -> None:
        await get_pool()

    async def execute(self, context: ToolContext, **kwargs) -> str:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO savings_transfers (user_id, amount, date, note)
                VALUES ($1, $2, $3::date, $4)
                RETURNING id, amount, date
                """,
                kwargs["user_id"],
                kwargs["amount"],
                kwargs["date"],
                kwargs.get("note"),
            )
        note_part = f" ({kwargs['note']})" if kwargs.get("note") else ""
        return (
            f"Saved ${row['amount']:.2f}{note_part} on {row['date'].isoformat()} "
            f"(id={row['id']})."
        )
