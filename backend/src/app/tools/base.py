"""Tool base helpers.

Every tool routes its output through `record_tool_result` so that the
session manager owns sizing, summarization, and persistence. The agent
sees only the metadata view (handle + summary + maybe inline payload).
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.session.manager import record_tool_result


def make_session_tool(
    *,
    name: str,
    description: str,
    args_schema: type[BaseModel],
    runner: Callable[..., Awaitable[str]],
    session_id_provider: Callable[[], str],
) -> StructuredTool:
    """Wrap an async runner into a LangChain StructuredTool that pipes
    its raw string output through the session manager."""

    async def _coro(**kwargs: Any) -> str:
        payload = await runner(**kwargs)
        view = await record_tool_result(
            session_id=session_id_provider(),
            tool_name=name,
            tool_args=kwargs,
            payload=payload,
        )
        return json.dumps(view)

    return StructuredTool.from_function(
        coroutine=_coro,
        name=name,
        description=description,
        args_schema=args_schema,
    )
