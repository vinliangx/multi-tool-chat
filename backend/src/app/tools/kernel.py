"""ToolKernel — the core orchestrator for all tool plugins."""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from langchain_core.tools import StructuredTool

from app.tools.middleware import ToolMiddleware
from app.tools.plugin import (
    KernelServices,
    ToolContext,
    ToolPlugin,
    _current_context,
)

_current_session: ContextVar[str] = ContextVar("session_id", default="")
_in_flight: ContextVar[frozenset[str]] = ContextVar(
    "tools_in_flight", default=frozenset()
)


class ToolCycleError(RuntimeError):
    pass


class ToolKernel:
    def __init__(self) -> None:
        self._plugins: dict[str, ToolPlugin] = {}
        self._middleware: list[ToolMiddleware] = []
        self.services = KernelServices()
        self._initialized = False

    def register(self, plugin: ToolPlugin) -> None:
        if plugin.name in self._plugins:
            raise ValueError(f"Tool '{plugin.name}' is already registered")
        self._plugins[plugin.name] = plugin

    def use(self, middleware: ToolMiddleware) -> None:
        self._middleware.append(middleware)

    @property
    def plugins(self) -> dict[str, ToolPlugin]:
        return dict(self._plugins)

    async def init(self) -> None:
        for plugin in self._plugins.values():
            await plugin.on_init(self)
        self._initialized = True

    async def shutdown(self) -> None:
        for plugin in reversed(list(self._plugins.values())):
            await plugin.on_shutdown()
        self._initialized = False

    async def execute_tool(
        self,
        name: str,
        context: ToolContext,
        **kwargs: Any,
    ) -> str:
        plugin = self._plugins.get(name)
        if plugin is None:
            return json.dumps({"error": f"unknown tool '{name}'"})

        in_flight = _in_flight.get()
        if name in in_flight:
            raise ToolCycleError(f"Cycle detected: tool '{name}' is already executing")
        _in_flight.set(in_flight | {name})

        start = time.monotonic()
        error: Exception | None = None
        result: str | None = None

        try:
            for mw in self._middleware:
                await mw.before_execute(context, plugin, kwargs)

            result = await plugin.execute(context, **kwargs)

            if not plugin.skip_result_processing and self.services.result is not None:
                result = json.dumps(
                    await self.services.result.process(
                        session_id=context.session_id,
                        tool_name=name,
                        tool_args=kwargs,
                        payload=result,
                    )
                )

            for mw in self._middleware:
                await mw.after_execute(
                    context, plugin, result, (time.monotonic() - start) * 1000
                )

        except Exception as e:
            error = e
            for mw in self._middleware:
                await mw.on_error(context, plugin, e)
            result = json.dumps({"error": str(e), "tool": name})

        finally:
            _in_flight.set(in_flight)
            if self.services.metrics is not None:
                await self.services.metrics.record_call(
                    tool_name=name,
                    duration_ms=(time.monotonic() - start) * 1000,
                    status="error" if error else "ok",
                    token_count=len(result or ""),
                )

        return result

    def build_langchain_tools(self) -> list[StructuredTool]:
        return [self._wrap_plugin(p) for p in self._plugins.values()]

    def _wrap_plugin(self, plugin: ToolPlugin) -> StructuredTool:
        async def _coro(**kwargs: Any) -> str:
            ctx = _current_context.get()
            return await self.execute_tool(plugin.name, ctx, **kwargs)

        return StructuredTool.from_function(
            coroutine=_coro,
            name=plugin.name,
            description=plugin.description,
            args_schema=plugin.args_schema,
        )

    @contextmanager
    def bind_context(self, session_id: str, user_id: str | None = None):
        ctx = ToolContext(
            session_id=session_id,
            user_id=user_id,
            request_id=uuid.uuid4().hex[:12],
            services=self.services,
            kernel=self,
        )
        token_ctx = _current_context.set(ctx)
        token_sess = _current_session.set(session_id)
        try:
            yield ctx
        finally:
            _current_context.reset(token_ctx)
            _current_session.reset(token_sess)


def get_current_session_id() -> str:
    return _current_session.get()
