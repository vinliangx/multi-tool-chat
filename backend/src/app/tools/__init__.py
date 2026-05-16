"""Tools package — micro kernel architecture for tool plugins."""

from app.tools.kernel import ToolKernel
from app.tools.plugins import ALL_PLUGINS
from app.tools.services.result import ResultProcessor
from app.tools.services.storage import StorageService
from app.tools.services.event_bus import EventBus
from app.tools.services.memory import MemoryService
from app.tools.services.cache import CacheService
from app.tools.services.metrics import MetricsService
from app.tools.middleware import LoggingMiddleware, ErrorHandlingMiddleware


def create_kernel() -> ToolKernel:
    kernel = ToolKernel()
    kernel.services.result = ResultProcessor()
    kernel.services.storage = StorageService()
    kernel.services.event_bus = EventBus()
    kernel.services.memory = MemoryService()
    kernel.services.cache = CacheService()
    kernel.services.metrics = MetricsService()

    for plugin in ALL_PLUGINS:
        kernel.register(plugin)

    return kernel


__all__ = [
    "ToolKernel",
    "create_kernel",
    "ALL_PLUGINS",
    "ResultProcessor",
    "StorageService",
    "EventBus",
    "MemoryService",
    "CacheService",
    "MetricsService",
    "LoggingMiddleware",
    "ErrorHandlingMiddleware",
]
