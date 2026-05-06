from __future__ import annotations

import os
import sqlite3

from pydantic import BaseModel, Field

from app.tools.base import make_session_tool

DEFAULT_DB = os.getenv("DEMO_SQLITE_PATH", "/tmp/demo.sqlite")


class SqlArgs(BaseModel):
    stmt: str = Field(..., description="A create, drop, alter table statement")


async def _run(
    stmt: str,
) -> str:
    conn = sqlite3.connect(DEFAULT_DB)
    try:
        cur = conn.cursor()
        cur.execute(stmt)
        conn.commit()
    except sqlite3.Error as exc:
        return f"sql error: {exc}"
    finally:
        conn.close()
    return "Executed successfully"


def factory(session_id_provider):
    return make_session_tool(
        name="sql_ddl",
        description="Run a SQL Statement to create, drop, alter tables for sqlite3.",
        args_schema=SqlArgs,
        runner=_run,
        session_id_provider=session_id_provider,
    )
