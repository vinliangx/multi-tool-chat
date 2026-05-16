"""EventBus — kernel-mediated inter-tool communication."""

from __future__ import annotations

import asyncio
from typing import Any, Callable


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Any]]] = {}

    async def publish(self, event: str, payload: dict[str, Any]) -> None:
        handlers = self._handlers.get(event, [])
        results: list[Any] = []
        for handler in handlers:
            r = handler(event=event, payload=payload)
            if asyncio.iscoroutine(r):
                r = await r
            results.append(r)
        return results

    def subscribe(self, event: str, handler: Callable[..., Any]) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def unsubscribe(self, event: str, handler: Callable[..., Any]) -> None:
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)
