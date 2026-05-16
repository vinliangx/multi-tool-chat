from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin
from app.tools.plugins.personal_finance.db import get_pool


class AddLoanArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")
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

    async def on_init(self, kernel) -> None:
        await get_pool()

    async def execute(self, context: ToolContext, **kwargs) -> str:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO loans
                    (user_id, name, original_amount, balance, apr, monthly_payment, due_date, start_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::date)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    original_amount = EXCLUDED.original_amount,
                    balance         = EXCLUDED.balance,
                    apr             = EXCLUDED.apr,
                    monthly_payment = EXCLUDED.monthly_payment,
                    due_date        = EXCLUDED.due_date,
                    start_date      = EXCLUDED.start_date,
                    updated_at      = now()
                RETURNING id, name
                """,
                kwargs["user_id"],
                kwargs["loan_name"],
                kwargs["original_amount"],
                kwargs["balance"],
                kwargs["apr"],
                kwargs["monthly_payment"],
                kwargs["due_date"],
                kwargs["start_date"],
            )
        return f"Loan '{row['name']}' saved (id={row['id']})."
