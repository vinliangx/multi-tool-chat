"""Async PostgreSQL pool and schema migrations for personal_finance."""
from __future__ import annotations

import os
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS credit_cards (
    id           SERIAL PRIMARY KEY,
    user_id      TEXT NOT NULL,
    name         TEXT NOT NULL,
    credit_limit NUMERIC(14,2) NOT NULL,
    apr          NUMERIC(7,4) NOT NULL,
    min_payment  NUMERIC(14,2) NOT NULL,
    cut_date     SMALLINT NOT NULL,
    due_date     SMALLINT NOT NULL,
    balance      NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS loans (
    id              SERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    original_amount NUMERIC(14,2) NOT NULL,
    balance         NUMERIC(14,2) NOT NULL,
    apr             NUMERIC(7,4) NOT NULL,
    monthly_payment NUMERIC(14,2) NOT NULL,
    due_date        SMALLINT NOT NULL,
    start_date      DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS income (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    amount     NUMERIC(14,2) NOT NULL,
    source     TEXT NOT NULL,
    month      SMALLINT NOT NULL,
    year       SMALLINT NOT NULL,
    recurring  BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS expenses (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    amount      NUMERIC(14,2) NOT NULL,
    description TEXT NOT NULL,
    date        DATE NOT NULL,
    category    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pending_conflicts (
    id             SERIAL PRIMARY KEY,
    user_id        TEXT NOT NULL,
    entry_type     TEXT NOT NULL,
    existing_entry JSONB NOT NULL,
    incoming_entry JSONB NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS savings_transfers (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    amount     NUMERIC(14,2) NOT NULL,
    date       DATE NOT NULL,
    note       TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        url = os.environ.get(
            "POSTGRES_URL",
            "postgresql://finance_user:finance_password@localhost:5432/finance_db",
        )
        _pool = await asyncpg.create_pool(url)
        async with _pool.acquire() as conn:
            await conn.execute(_SCHEMA)
    return _pool


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return dict(row)
