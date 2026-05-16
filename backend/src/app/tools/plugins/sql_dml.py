import os
import sqlite3

from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

DEFAULT_DB = os.getenv("DEMO_SQLITE_PATH", "/tmp/demo.sqlite")


class SqlDmlArgs(BaseModel):
    queries: list[str] = Field(
        ..., description="A list of DML Insert, Update or Delete"
    )


class SqlDmlPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "sql_dml"

    @property
    def description(self) -> str:
        return "Run SQL insert, update and delete on a table for sqlite3"

    @property
    def args_schema(self) -> type[BaseModel]:
        return SqlDmlArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        queries = kwargs["queries"]
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
