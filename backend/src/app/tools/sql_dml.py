from __future__ import annotations

import os
import sqlite3

from pydantic import BaseModel, Field

from app.tools.base import make_session_tool

# This Demo not for Production
DEFAULT_DB = os.getenv("DEMO_SQLITE_PATH", "/tmp/demo.sqlite")


class SqlArgs(BaseModel):
    queries: list[str] = Field(
        ..., description="A list of DML Insert, Update or Delete"
    )


async def _run(queries: list[str]) -> str:
    conn = sqlite3.connect(DEFAULT_DB)
    try:
        cur = conn.cursor()
        for query in queries:
            stripped = query.strip().lower()
            if (
                not stripped.startswith("insert")
                and not stripped.startswith("update")
                and not stripped.startswith("delete")
            ):
                return "error: only Insert/Update/Delete queries are allowed"
            cur.execute(query)
        conn.commit()
    except sqlite3.Error as exc:
        return f"sql error: {exc}"
    finally:
        conn.close()

    return "Completed successfully"


def factory(session_id_provider):
    return make_session_tool(
        name="sql_dml",
        description="Run SQL insert, update and delete on a table for sqlite3",
        args_schema=SqlArgs,
        runner=_run,
        session_id_provider=session_id_provider,
    )
