"""Tool plugin interface, context, and kernel services container."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.tools.kernel import ToolKernel
    from app.tools.services.cache import CacheService
    from app.tools.services.event_bus import EventBus
    from app.tools.services.memory import MemoryService
    from app.tools.services.metrics import MetricsService
    from app.tools.services.result import ResultProcessor
    from app.tools.services.storage import StorageService


_current_context: ContextVar["ToolContext"] = ContextVar("tool_context")


def get_current_context() -> "ToolContext":
    return _current_context.get()


@dataclass
class KernelServices:
    result: ResultProcessor | None = None
    storage: StorageService | None = None
    event_bus: EventBus | None = None
    memory: MemoryService | None = None
    cache: CacheService | None = None
    metrics: MetricsService | None = None


@dataclass
class ToolContext:
    session_id: str
    user_id: str | None
    request_id: str
    services: KernelServices
    kernel: ToolKernel

    async def call_tool(self, name: str, /, **kwargs: Any) -> str:
        return await self.kernel.execute_tool(name, self, **kwargs)


class ToolPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def args_schema(self) -> type[BaseModel]: ...

    @property
    def skip_result_processing(self) -> bool:
        return False

    @abstractmethod
    async def execute(self, context: ToolContext, **kwargs: Any) -> str: ...

    async def on_init(self, kernel: "ToolKernel") -> None:
        pass

    async def on_shutdown(self) -> None:
        pass

    async def on_health(self) -> dict[str, Any]:
        return {}
