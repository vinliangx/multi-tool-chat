from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin


class ReadMemoryArgs(BaseModel):
    user_id: str = Field(
        ...,
        description="The name which the user identifies itself, like 'My name is John' for example",
    )


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
        user_id = kwargs["user_id"]
        data = (
            await context.services.memory.get_user_memory(user_id)
            if context.services.memory
            else None
        )
        if data is not None:
            import json

            return json.dumps(data)
        return "{}"
