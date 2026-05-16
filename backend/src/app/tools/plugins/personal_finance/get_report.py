import calendar
from datetime import date

from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin
from app.tools.plugins.personal_finance.db import get_pool


class GetReportArgs(BaseModel):
    user_id: str = Field(..., description="User identifier")


class GetReportPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "get_report"

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

    async def on_init(self, kernel) -> None:
        await get_pool()

    async def execute(self, context: ToolContext, **kwargs) -> str:
        user_id = kwargs["user_id"]
        today = date.today()
        month, year = today.month, today.year
        days_in_month = calendar.monthrange(year, month)[1]
        days_remaining = days_in_month - today.day + 1

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Explicit income for this month
            explicit_income: float = float(
                await conn.fetchval(
                    "SELECT COALESCE(SUM(amount), 0) FROM income WHERE user_id=$1 AND month=$2 AND year=$3",
                    user_id, month, year,
                )
            )

            # Recurring income from earlier months not already covered by an explicit entry
            recurring_rows = await conn.fetch(
                """
                SELECT DISTINCT ON (lower(source)) source, amount
                FROM income
                WHERE user_id=$1
                  AND recurring = true
                  AND NOT (month=$2 AND year=$3)
                ORDER BY lower(source), year DESC, month DESC
                """,
                user_id, month, year,
            )
            explicit_sources_rows = await conn.fetch(
                "SELECT lower(source) AS src FROM income WHERE user_id=$1 AND month=$2 AND year=$3",
                user_id, month, year,
            )
            explicit_sources = {r["src"] for r in explicit_sources_rows}
            recurring_income = sum(
                float(r["amount"])
                for r in recurring_rows
                if r["source"].lower() not in explicit_sources
            )

            total_income = explicit_income + recurring_income

            # Expenses for this calendar month
            total_expenses: float = float(
                await conn.fetchval(
                    """
                    SELECT COALESCE(SUM(amount), 0) FROM expenses
                    WHERE user_id=$1
                      AND date >= $2::date
                      AND date <= $3::date
                    """,
                    user_id,
                    date(year, month, 1),
                    date(year, month, days_in_month),
                )
            )

            # Credit card snapshots
            cc_rows = await conn.fetch(
                """
                SELECT name, balance, credit_limit, apr, min_payment, due_date
                FROM credit_cards
                WHERE user_id=$1
                ORDER BY name
                """,
                user_id,
            )

            # Loan snapshots
            loan_rows = await conn.fetch(
                """
                SELECT name, balance, original_amount, apr, monthly_payment, due_date
                FROM loans
                WHERE user_id=$1
                ORDER BY name
                """,
                user_id,
            )

            # Savings transfers this month
            savings_rows = await conn.fetch(
                """
                SELECT amount, date, note
                FROM savings_transfers
                WHERE user_id=$1
                  AND date >= $2::date
                  AND date <= $3::date
                ORDER BY date
                """,
                user_id,
                date(year, month, 1),
                date(year, month, days_in_month),
            )
            total_savings = float(
                await conn.fetchval(
                    """
                    SELECT COALESCE(SUM(amount), 0)
                    FROM savings_transfers
                    WHERE user_id=$1
                    """,
                    user_id,
                )
            )

        burn_rate = (total_expenses / total_income * 100) if total_income > 0 else 0.0
        remaining = total_income - total_expenses
        daily_budget = remaining / days_remaining if days_remaining > 0 else 0.0

        lines = [
            f"=== Financial Report: {today.strftime('%B %Y')} ===",
            f"Total income : ${total_income:>12,.2f}",
            f"Total expenses: ${total_expenses:>11,.2f}",
            f"Remaining    : ${remaining:>12,.2f}",
            f"Burn rate    : {burn_rate:>11.1f}%",
            f"Days remaining: {days_remaining}",
            f"Daily budget : ${daily_budget:>12,.2f}",
        ]

        if cc_rows:
            lines.append("\n--- Credit Cards ---")
            total_cc_balance = 0.0
            total_cc_limit = 0.0
            for r in cc_rows:
                balance = float(r["balance"])
                limit = float(r["credit_limit"])
                utilization = (balance / limit * 100) if limit > 0 else 0.0
                available = limit - balance
                total_cc_balance += balance
                total_cc_limit += limit
                lines.append(
                    f"  {r['name']:<24} balance ${balance:>9,.2f} / ${limit:>9,.2f}  "
                    f"util {utilization:>5.1f}%  avail ${available:>9,.2f}  "
                    f"APR {float(r['apr']):.2f}%  min ${float(r['min_payment']):>7,.2f}  due day {r['due_date']}"
                )
            overall_util = (total_cc_balance / total_cc_limit * 100) if total_cc_limit > 0 else 0.0
            lines.append(
                f"  {'TOTAL':<24} balance ${total_cc_balance:>9,.2f} / ${total_cc_limit:>9,.2f}  "
                f"util {overall_util:>5.1f}%"
            )

        if loan_rows:
            lines.append("\n--- Loans ---")
            total_loan_balance = 0.0
            for r in loan_rows:
                balance = float(r["balance"])
                original = float(r["original_amount"])
                paid_pct = ((original - balance) / original * 100) if original > 0 else 0.0
                total_loan_balance += balance
                lines.append(
                    f"  {r['name']:<24} balance ${balance:>9,.2f} / ${original:>9,.2f}  "
                    f"paid {paid_pct:>5.1f}%  "
                    f"APR {float(r['apr']):.2f}%  pmt ${float(r['monthly_payment']):>7,.2f}  due day {r['due_date']}"
                )
            lines.append(f"  {'TOTAL LOAN BALANCE':<24} ${total_loan_balance:>9,.2f}")

        month_savings = sum(float(r["amount"]) for r in savings_rows)
        lines.append("\n--- Savings ---")
        if savings_rows:
            for r in savings_rows:
                note_part = f"  {r['note']}" if r["note"] else ""
                lines.append(
                    f"  {r['date'].isoformat()}  ${float(r['amount']):>9,.2f}{note_part}"
                )
        lines.append(f"  {'This month':<24} ${month_savings:>9,.2f}")
        lines.append(f"  {'All time':<24} ${total_savings:>9,.2f}")

        return "\n".join(lines)
