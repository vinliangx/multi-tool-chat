from __future__ import annotations

import calendar
import json
import logging
from contextlib import asynccontextmanager
from datetime import date as _date
from typing import Literal

import db
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

logging.basicConfig(level=logging.INFO)

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


@asynccontextmanager
async def lifespan(app):
    await db.get_pool()
    try:
        yield
    finally:
        await db.close_pool()


mcp = FastMCP("Personal Finance", lifespan=lifespan)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool(name="add_credit_card")
async def add_credit_card(
    user_id: str,
    cc_name: str,
    credit_limit: float,
    apr: float,
    min_payment: float,
    cut_date: int,
    due_date: int,
    balance: float = 0.0,
) -> str:
    """Add or update a credit card account. If a card with the same name already exists for the user it is updated in place."""
    pool = await db.get_pool()
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
            user_id, cc_name, credit_limit, apr, min_payment, cut_date, due_date, balance,
        )
    return f"Credit card '{row['name']}' saved (id={row['id']})."


@mcp.tool(name="add_loan")
async def add_loan(
    user_id: str,
    loan_name: str,
    original_amount: float,
    balance: float,
    apr: float,
    monthly_payment: float,
    due_date: int,
    start_date: str,
) -> str:
    """Add or update a loan account. If a loan with the same name already exists for the user it is updated in place."""
    pool = await db.get_pool()
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
            user_id, loan_name, original_amount, balance, apr, monthly_payment, due_date, start_date,
        )
    return f"Loan '{row['name']}' saved (id={row['id']})."


@mcp.tool(name="add_income")
async def add_income(
    user_id: str,
    amount: float,
    source: str,
    month: int,
    year: int,
    recurring: bool = False,
    force: bool = False,
) -> str:
    """Record an income entry for a given month. Checks for duplicates (same user, amount, source, month, year) before inserting. Set force=true to override a detected duplicate."""
    pool = await db.get_pool()
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
                    user_id, json.dumps(existing_dict), json.dumps(incoming),
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


@mcp.tool(name="add_expense")
async def add_expense(
    user_id: str,
    amount: float,
    description: str,
    date: str,
    category: CATEGORIES,
    force: bool = False,
) -> str:
    """Record an expense. Checks for duplicates (same user, amount, date, description — case-insensitive) before inserting. Set force=true to override a detected duplicate."""
    pool = await db.get_pool()
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
                user_id, amount, description, date,
            )
            if existing is not None:
                incoming = {
                    "amount": amount,
                    "description": description,
                    "date": date,
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
                    user_id, json.dumps(existing_dict), json.dumps(incoming),
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
            user_id, amount, description, date, category,
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
                user_id, amount, description, date,
            )

    return (
        f"Expense saved (id={row['id']}): ${amount:,.2f} — '{description}' "
        f"on {date} [{category}]."
    )


@mcp.tool(name="payment_to_credit_card")
async def payment_to_credit_card(user_id: str, cc_name: str, amount: float) -> str:
    """Record a payment toward a credit card balance. Reduces the card's outstanding balance by the payment amount."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE credit_cards
            SET balance    = GREATEST(balance - $3, 0),
                updated_at = now()
            WHERE user_id = $1 AND name = $2
            RETURNING name, balance
            """,
            user_id, cc_name, amount,
        )
    if row is None:
        return f"Credit card '{cc_name}' not found for user '{user_id}'."
    return (
        f"Payment of ${amount:.2f} applied to '{row['name']}'. "
        f"New balance: ${row['balance']:.2f}."
    )


@mcp.tool(name="payment_to_loan")
async def payment_to_loan(user_id: str, loan_name: str, amount: float) -> str:
    """Record a payment toward a loan balance. Reduces the loan's remaining balance by the payment amount."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE loans
            SET balance    = GREATEST(balance - $3, 0),
                updated_at = now()
            WHERE user_id = $1 AND name = $2
            RETURNING name, balance
            """,
            user_id, loan_name, amount,
        )
    if row is None:
        return f"Loan '{loan_name}' not found for user '{user_id}'."
    return (
        f"Payment of ${amount:.2f} applied to '{row['name']}'. "
        f"Remaining balance: ${row['balance']:.2f}."
    )


@mcp.tool(name="get_report")
async def get_report(user_id: str) -> str:
    """Generate a financial summary for the current calendar month: burn rate (% of income spent) and daily budget (remaining income / remaining days). Recurring income from prior months is projected forward when no explicit entry exists."""
    today = _date.today()
    month, year = today.month, today.year
    days_in_month = calendar.monthrange(year, month)[1]
    days_remaining = days_in_month - today.day + 1

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        explicit_income: float = float(
            await conn.fetchval(
                "SELECT COALESCE(SUM(amount), 0) FROM income WHERE user_id=$1 AND month=$2 AND year=$3",
                user_id, month, year,
            )
        )

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

        total_expenses: float = float(
            await conn.fetchval(
                """
                SELECT COALESCE(SUM(amount), 0) FROM expenses
                WHERE user_id=$1
                  AND date >= $2::date
                  AND date <= $3::date
                """,
                user_id,
                _date(year, month, 1),
                _date(year, month, days_in_month),
            )
        )

        cc_rows = await conn.fetch(
            """
            SELECT name, balance, credit_limit, apr, min_payment, due_date
            FROM credit_cards
            WHERE user_id=$1
            ORDER BY name
            """,
            user_id,
        )

        loan_rows = await conn.fetch(
            """
            SELECT name, balance, original_amount, apr, monthly_payment, due_date
            FROM loans
            WHERE user_id=$1
            ORDER BY name
            """,
            user_id,
        )

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
            _date(year, month, 1),
            _date(year, month, days_in_month),
        )
        total_savings = float(
            await conn.fetchval(
                "SELECT COALESCE(SUM(amount), 0) FROM savings_transfers WHERE user_id=$1",
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


@mcp.tool(name="list_conflicts")
async def list_conflicts(user_id: str) -> str:
    """List all pending duplicate-transaction conflicts for the user. Each conflict shows the existing entry and the incoming entry that was blocked. To resolve: call add_income or add_expense with force=true to keep both entries, or simply discard the incoming entry by doing nothing."""
    pool = await db.get_pool()
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


@mcp.tool(name="transferred_to_savings")
async def transferred_to_savings(
    user_id: str,
    amount: float,
    date: str | None = None,
    note: str | None = None,
) -> str:
    """Record money transferred to savings. Tracked independently — does not affect any credit card or loan balance."""
    if date is None:
        date = _date.today().isoformat()
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO savings_transfers (user_id, amount, date, note)
            VALUES ($1, $2, $3::date, $4)
            RETURNING id, amount, date
            """,
            user_id, amount, date, note,
        )
    note_part = f" ({note})" if note else ""
    return (
        f"Saved ${row['amount']:.2f}{note_part} on {row['date'].isoformat()} "
        f"(id={row['id']})."
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8004)
