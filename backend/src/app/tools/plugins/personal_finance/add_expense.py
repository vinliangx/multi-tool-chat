import json
from typing import Literal

from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin
from app.tools.plugins.personal_finance.db import get_pool

CATEGORIES = Literal[
    "Housing",
    "Food & Groceries",
    "Transport",
    "Utilities",
    "Health",
    "Entertainment",
    "Debt Payment",
    "Other",
]


class AddExpenseArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")
    amount: float = Field(..., description="Expense amount in dollars")
    description: str = Field(..., description="Short label for the expense")
    date: str = Field(..., description="Date of the expense in YYYY-MM-DD format")
    category: CATEGORIES = Field(..., description="Expense category")
    force: bool = Field(
        False,
        description="Set to true to proceed with insertion even if a duplicate is detected",
    )


class AddExpensePlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "personal_finance.add_expense"

    @property
    def description(self) -> str:
        return (
            "Record an expense. Checks for duplicates "
            "(same user, amount, date, description — case-insensitive) before inserting. "
            "Set force=true to override a detected duplicate."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return AddExpenseArgs

    async def on_init(self, kernel) -> None:
        await get_pool()

    async def execute(self, context: ToolContext, **kwargs) -> str:
        user_id = kwargs["user_id"]
        amount = kwargs["amount"]
        description = kwargs["description"]
        date_str = kwargs["date"]
        category = kwargs["category"]
        force = kwargs.get("force", False)

        pool = await get_pool()
        async with pool.acquire() as conn:
            if not force:
                existing = await conn.fetchrow(
                    """
                    SELECT id, amount, description, date, category
                    FROM expenses
                    WHERE user_id=$1
                      AND amount=$2
                      AND lower(description)=lower($3)
                      AND date=$4::date
                    LIMIT 1
                    """,
                    user_id,
                    amount,
                    description,
                    date_str,
                )
                if existing is not None:
                    incoming = {
                        "amount": amount,
                        "description": description,
                        "date": date_str,
                        "category": category,
                    }
                    existing_dict = {
                        "id": existing["id"],
                        "amount": float(existing["amount"]),
                        "description": existing["description"],
                        "date": str(existing["date"]),
                        "category": existing["category"],
                    }
                    await conn.execute(
                        """
                        INSERT INTO pending_conflicts (user_id, entry_type, existing_entry, incoming_entry)
                        VALUES ($1, 'expense', $2::jsonb, $3::jsonb)
                        """,
                        user_id,
                        json.dumps(existing_dict),
                        json.dumps(incoming),
                    )
                    return (
                        f"Duplicate expense detected.\n"
                        f"  Existing: {existing_dict}\n"
                        f"  Incoming: {incoming}\n"
                        "Call add_expense again with force=true to save as a new entry, "
                        "or use list_conflicts to review all pending conflicts."
                    )

            row = await conn.fetchrow(
                """
                INSERT INTO expenses (user_id, amount, description, date, category)
                VALUES ($1, $2, $3, $4::date, $5)
                RETURNING id
                """,
                user_id,
                amount,
                description,
                date_str,
                category,
            )
            if force:
                await conn.execute(
                    """
                    DELETE FROM pending_conflicts
                    WHERE user_id=$1
                      AND entry_type='expense'
                      AND (existing_entry->>'amount')::numeric=$2
                      AND lower(existing_entry->>'description')=lower($3)
                      AND existing_entry->>'date'=$4
                    """,
                    user_id,
                    amount,
                    description,
                    date_str,
                )

        return (
            f"Expense saved (id={row['id']}): ${amount:,.2f} — '{description}' "
            f"on {date_str} [{category}]."
        )
