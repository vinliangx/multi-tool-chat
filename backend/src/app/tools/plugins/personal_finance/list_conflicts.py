from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin
from app.tools.plugins.personal_finance.db import get_pool


class ListConflictsArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")


class ListConflictsPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "list_conflicts"

    @property
    def description(self) -> str:
        return (
            "List all pending duplicate-transaction conflicts for the user. "
            "Each conflict shows the existing entry and the incoming entry that was blocked. "
            "To resolve: call add_income or add_expense with force=true to keep both entries, "
            "or simply discard the incoming entry by doing nothing."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return ListConflictsArgs

    async def on_init(self, kernel) -> None:
        await get_pool()

    async def execute(self, context: ToolContext, **kwargs) -> str:
        user_id = kwargs["user_id"]
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, entry_type, existing_entry, incoming_entry, created_at
                FROM pending_conflicts
                WHERE user_id=$1
                ORDER BY created_at DESC
                """,
                user_id,
            )

        if not rows:
            return "No pending conflicts."

        lines = [f"{len(rows)} pending conflict(s):\n"]
        for row in rows:
            lines.append(
                f"[#{row['id']}] type={row['entry_type']}  detected={row['created_at'].strftime('%Y-%m-%d %H:%M')}\n"
                f"  Existing : {dict(row['existing_entry'])}\n"
                f"  Incoming : {dict(row['incoming_entry'])}\n"
            )
        return "\n".join(lines)
