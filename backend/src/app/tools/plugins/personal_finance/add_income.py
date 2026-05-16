import json

from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin
from app.tools.plugins.personal_finance.db import get_pool


class AddIncomeArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")
    amount: float = Field(..., description="Income amount in dollars")
    source: str = Field(..., description="Source label, e.g. 'Salary', 'Freelance'")
    month: int = Field(..., ge=1, le=12, description="Month the income applies to (1-12)")
    year: int = Field(..., ge=2000, description="Year the income applies to")
    recurring: bool = Field(False, description="If true, auto-projects into subsequent months")
    force: bool = Field(
        False,
        description="Set to true to proceed with insertion even if a duplicate is detected",
    )


class AddIncomePlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "add_income"

    @property
    def description(self) -> str:
        return (
            "Record an income entry for a given month. Checks for duplicates "
            "(same user, amount, source, month, year) before inserting. "
            "Set force=true to override a detected duplicate."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return AddIncomeArgs

    async def on_init(self, kernel) -> None:
        await get_pool()

    async def execute(self, context: ToolContext, **kwargs) -> str:
        user_id = kwargs["user_id"]
        amount = kwargs["amount"]
        source = kwargs["source"]
        month = kwargs["month"]
        year = kwargs["year"]
        recurring = kwargs["recurring"]
        force = kwargs.get("force", False)

        pool = await get_pool()
        async with pool.acquire() as conn:
            if not force:
                existing = await conn.fetchrow(
                    """
                    SELECT id, amount, source, month, year, recurring
                    FROM income
                    WHERE user_id=$1
                      AND amount=$2
                      AND lower(source)=lower($3)
                      AND month=$4
                      AND year=$5
                    LIMIT 1
                    """,
                    user_id, amount, source, month, year,
                )
                if existing is not None:
                    incoming = {
                        "amount": amount,
                        "source": source,
                        "month": month,
                        "year": year,
                        "recurring": recurring,
                    }
                    existing_dict = {
                        "id": existing["id"],
                        "amount": float(existing["amount"]),
                        "source": existing["source"],
                        "month": existing["month"],
                        "year": existing["year"],
                        "recurring": existing["recurring"],
                    }
                    await conn.execute(
                        """
                        INSERT INTO pending_conflicts (user_id, entry_type, existing_entry, incoming_entry)
                        VALUES ($1, 'income', $2::jsonb, $3::jsonb)
                        """,
                        user_id,
                        json.dumps(existing_dict),
                        json.dumps(incoming),
                    )
                    return (
                        f"Duplicate income detected.\n"
                        f"  Existing: {existing_dict}\n"
                        f"  Incoming: {incoming}\n"
                        "Call add_income again with force=true to save as a new entry, "
                        "or use list_conflicts to review all pending conflicts."
                    )

            row = await conn.fetchrow(
                """
                INSERT INTO income (user_id, amount, source, month, year, recurring)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                user_id, amount, source, month, year, recurring,
            )
            # Clear matching conflicts that were resolved by force
            if force:
                await conn.execute(
                    """
                    DELETE FROM pending_conflicts
                    WHERE user_id=$1
                      AND entry_type='income'
                      AND (existing_entry->>'amount')::numeric=$2
                      AND lower(existing_entry->>'source')=lower($3)
                      AND (existing_entry->>'month')::int=$4
                      AND (existing_entry->>'year')::int=$5
                    """,
                    user_id, amount, source, month, year,
                )

        return f"Income entry saved (id={row['id']}): ${amount:,.2f} from '{source}' for {month}/{year}."
