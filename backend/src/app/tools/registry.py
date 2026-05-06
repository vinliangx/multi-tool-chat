from __future__ import annotations

from typing import Callable

from langchain_core.tools import BaseTool

from app.tools import (
    csv_s3,
    http_fetch,
    read_memory,
    recall,
    save_memory,
    sql_ddl,
    sql_dml,
    sql_query,
    weather_api,
)

ALL_TOOL_FACTORIES = [
    http_fetch.factory,
    csv_s3.factory,
    sql_query.factory,
    weather_api.factory,
    recall.factory,
    sql_ddl.factory,
    sql_dml.factory,
    save_memory.factory,
    read_memory.factory,
]


def build_tools(session_id_provider: Callable[[], str]) -> list[BaseTool]:
    return [f(session_id_provider) for f in ALL_TOOL_FACTORIES]
