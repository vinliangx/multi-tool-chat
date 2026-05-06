from __future__ import annotations

import os
import sqlite3

from pydantic import BaseModel, Field

from app.tools.base import make_session_tool

DEFAULT_DB = os.getenv("DEMO_SQLITE_PATH", "/tmp/demo.sqlite")


class SqlArgs(BaseModel):
    query: str = Field(
        ..., description="A read-only SQL query for SQLite (SELECT only)."
    )
    limit: int = Field(200, description="Max rows to return")


async def _run(query: str, limit: int = 200) -> str:
    stripped = query.strip().lower()
    if not stripped.startswith("select") and not stripped.startswith("with"):
        return "error: only SELECT/WITH queries are allowed"
    conn = sqlite3.connect(DEFAULT_DB)
    try:
        cur = conn.cursor()
        cur.execute(query)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(limit)
        if len(rows) == 0:
            return "No rows available"
    except sqlite3.Error as exc:
        return f"sql error: {exc}"
    finally:
        conn.close()

    lines = [",".join(cols)]
    for row in rows:
        lines.append(",".join("" if v is None else str(v) for v in row))
    return "\n".join(lines)


def factory(session_id_provider):
    return make_session_tool(
        name="sql_query",
        description="Run a read-only SQL query against the demo database for sqlite3",
        args_schema=SqlArgs,
        runner=_run,
        session_id_provider=session_id_provider,
    )
