import json

from pydantic import BaseModel

from app.tools.plugin import ToolContext, ToolPlugin


class ReadMemoryArgs(BaseModel):
    pass


class ReadMemoryPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "read_memory"

    @property
    def description(self) -> str:
        return "Read facts, likes and dislikes from User whenever presented"

    @property
    def args_schema(self) -> type[BaseModel]:
        return ReadMemoryArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        user_id = context.user_id
        if not user_id:
            return "{}"
        data = (
            await context.services.memory.get_user_memory(user_id)
            if context.services.memory
            else None
        )
        if data is not None:
            return json.dumps(data)
        return "{}"
