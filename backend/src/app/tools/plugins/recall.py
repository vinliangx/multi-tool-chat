"""Recall plugin — the agent's explicit way to bring a stored result back."""

from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin


class RecallArgs(BaseModel):
    handle: str = Field(
        ...,
        description="The handle returned by an earlier tool call (e.g. 'tr_abc123').",
    )


class RecallPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "recall"

    @property
    def description(self) -> str:
        return (
            "Bring the full payload of a previously stored tool result back into context. "
            "Use this when the summary you have is not enough and you need raw detail. "
            "Pass the 'handle' you received from the earlier tool call."
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return RecallArgs

    @property
    def skip_result_processing(self) -> bool:
        return True

    async def execute(self, context: ToolContext, **kwargs) -> str:
        handle = kwargs["handle"]
        if context.services.result is None:
            return "error: result service not available"
        payload, rec = await context.services.result.recall(handle)
        if rec is None:
            return f"unknown handle: {handle}"
        head = (
            f"recalled tool={rec.tool_name} args={rec.tool_args} "
            f"size={rec.payload_size_bytes}B tokens~{rec.token_estimate}\n\n"
        )
        return head + (payload or "")
