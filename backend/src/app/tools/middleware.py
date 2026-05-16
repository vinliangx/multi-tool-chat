"""Middleware interface and built-in implementations for the tool kernel."""

from __future__ import annotations

import logging
from abc import ABC
from typing import Any

from app.tools.plugin import ToolContext, ToolPlugin

logger = logging.getLogger(__name__)


class ToolMiddleware(ABC):
    async def before_execute(
        self, context: ToolContext, tool: ToolPlugin, kwargs: dict[str, Any]
    ) -> None:
        pass

    async def after_execute(
        self,
        context: ToolContext,
        tool: ToolPlugin,
        result: str,
        duration_ms: float,
    ) -> None:
        pass

    async def on_error(
        self, context: ToolContext, tool: ToolPlugin, error: Exception
    ) -> None:
        pass


class LoggingMiddleware(ToolMiddleware):
    async def before_execute(
        self, context: ToolContext, tool: ToolPlugin, kwargs: dict[str, Any]
    ) -> None:
        logger.info(
            "tool_call session=%s tool=%s args=%s",
            context.session_id,
            tool.name,
            kwargs,
        )

    async def after_execute(
        self,
        context: ToolContext,
        tool: ToolPlugin,
        result: str,
        duration_ms: float,
    ) -> None:
        logger.info(
            "tool_result session=%s tool=%s duration=%.0fms size=%d",
            context.session_id,
            tool.name,
            duration_ms,
            len(result),
        )

    async def on_error(
        self, context: ToolContext, tool: ToolPlugin, error: Exception
    ) -> None:
        logger.error(
            "tool_error session=%s tool=%s error=%s",
            context.session_id,
            tool.name,
            error,
        )


class ErrorHandlingMiddleware(ToolMiddleware):
    async def on_error(
        self, context: ToolContext, tool: ToolPlugin, error: Exception
    ) -> None:
        logger.exception(
            "Unhandled error in tool '%s' (session=%s): %s",
            tool.name,
            context.session_id,
            error,
        )
