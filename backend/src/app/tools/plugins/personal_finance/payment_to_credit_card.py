from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin
from app.tools.plugins.personal_finance.db import get_pool


class PaymentToCreditCardArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")
    cc_name: str = Field(..., description="Card name / issuer, e.g. 'Chase Sapphire'")
    amount: float = Field(..., gt=0, description="Payment amount in dollars")


class PaymentToCreditCardPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.payment_to_credit_card"

    @property
    def description(self) -> str:
        return (
            "Record a payment toward a credit card balance. "
            "Reduces the card's outstanding balance by the payment amount."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return PaymentToCreditCardArgs

    async def on_init(self, kernel) -> None:
        await get_pool()

    async def execute(self, context: ToolContext, **kwargs) -> str:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE credit_cards
                SET balance    = GREATEST(balance - $3, 0),
                    updated_at = now()
                WHERE user_id = $1 AND name = $2
                RETURNING name, balance
                """,
                kwargs["user_id"],
                kwargs["cc_name"],
                kwargs["amount"],
            )
        if row is None:
            return f"Credit card '{kwargs['cc_name']}' not found for user '{kwargs['user_id']}'."
        return (
            f"Payment of ${kwargs['amount']:.2f} applied to '{row['name']}'. "
            f"New balance: ${row['balance']:.2f}."
        )
