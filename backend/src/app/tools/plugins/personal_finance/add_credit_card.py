from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin
from app.tools.plugins.personal_finance.db import get_pool


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
        return "add_credit_card"

    @property
    def description(self) -> str:
        return (
            "Add or update a credit card account. If a card with the same name already "
            "exists for the user it is updated in place."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return AddCreditCardArgs

    async def on_init(self, kernel) -> None:
        await get_pool()

    async def execute(self, context: ToolContext, **kwargs) -> str:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO credit_cards
                    (user_id, name, credit_limit, apr, min_payment, cut_date, due_date, balance)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    credit_limit = EXCLUDED.credit_limit,
                    apr          = EXCLUDED.apr,
                    min_payment  = EXCLUDED.min_payment,
                    cut_date     = EXCLUDED.cut_date,
                    due_date     = EXCLUDED.due_date,
                    balance      = EXCLUDED.balance,
                    updated_at   = now()
                RETURNING id, name
                """,
                kwargs["user_id"],
                kwargs["cc_name"],
                kwargs["credit_limit"],
                kwargs["apr"],
                kwargs["min_payment"],
                kwargs["cut_date"],
                kwargs["due_date"],
                kwargs["balance"],
            )
        return f"Credit card '{row['name']}' saved (id={row['id']})."
