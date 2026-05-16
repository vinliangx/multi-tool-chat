from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin
from app.tools.plugins.personal_finance.db import get_pool


class PaymentToLoanArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")
    loan_name: str = Field(..., description="Loan label, e.g. 'Car loan'")
    amount: float = Field(..., gt=0, description="Payment amount in dollars")


class PaymentToLoanPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "payment_to_loan"

    @property
    def description(self) -> str:
        return (
            "Record a payment toward a loan balance. "
            "Reduces the loan's remaining balance by the payment amount."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return PaymentToLoanArgs

    async def on_init(self, kernel) -> None:
        await get_pool()

    async def execute(self, context: ToolContext, **kwargs) -> str:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE loans
                SET balance    = GREATEST(balance - $3, 0),
                    updated_at = now()
                WHERE user_id = $1 AND name = $2
                RETURNING name, balance
                """,
                kwargs["user_id"],
                kwargs["loan_name"],
                kwargs["amount"],
            )
        if row is None:
            return f"Loan '{kwargs['loan_name']}' not found for user '{kwargs['user_id']}'."
        return (
            f"Payment of ${kwargs['amount']:.2f} applied to '{row['name']}'. "
            f"Remaining balance: ${row['balance']:.2f}."
        )
