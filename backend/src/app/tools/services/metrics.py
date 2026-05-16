"""MetricsService — collects execution data for tool calls."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolCallMetric:
    tool_name: str
    duration_ms: float
    status: str
    token_count: int


class MetricsService:
    def __init__(self) -> None:
        self._calls: list[ToolCallMetric] = []

    async def record_call(
        self,
        tool_name: str,
        duration_ms: float,
        status: str,
        token_count: int,
    ) -> None:
        self._calls.append(
            ToolCallMetric(
                tool_name=tool_name,
                duration_ms=duration_ms,
                status=status,
                token_count=token_count,
            )
        )

    def get_calls(self, tool_name: str | None = None) -> list[ToolCallMetric]:
        if tool_name is None:
            return list(self._calls)
        return [c for c in self._calls if c.tool_name == tool_name]

    def clear(self) -> None:
        self._calls.clear()
