"""CacheService — wraps the semantic cache for tool access."""

from __future__ import annotations

from typing import Any


class CacheService:
    def __init__(self) -> None:
        self._cache: Any = None

    def set_backend(self, cache: Any) -> None:
        self._cache = cache

    async def check(self, prompt: str, distance_threshold: float = 0.09) -> str | None:
        if self._cache is None:
            return None
        result = self._cache.check(prompt=prompt, distance_threshold=distance_threshold)
        if result:
            return result[0]["response"]
        return None

    async def store(self, prompt: str, response: str) -> None:
        if self._cache is not None:
            self._cache.store(prompt=prompt, response=response)
