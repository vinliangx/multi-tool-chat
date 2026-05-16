import os
import sqlite3

from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

DEFAULT_DB = os.getenv("DEMO_SQLITE_PATH", "/tmp/demo.sqlite")


class SqlDdlArgs(BaseModel):
    stmt: str = Field(..., description="A create, drop, alter table statement")


class SqlDdlPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "sql_ddl"

    @property
    def description(self) -> str:
        return "Run a SQL Statement to create, drop, alter tables for sqlite3."

    @property
    def args_schema(self) -> type[BaseModel]:
        return SqlDdlArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        stmt = kwargs["stmt"]
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
