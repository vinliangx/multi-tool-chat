from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin


class SaveMemoryArgs(BaseModel):
    facts: list[str] = Field(
        ..., description="List of facts of the user, besides his/her name"
    )
    likes: list[str] = Field(..., description="List of likes")
    dislikes: list[str] = Field(..., description="List of dislikes")


class SaveMemoryPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "save_memory"

    @property
    def description(self) -> str:
        return "Store facts, likes and dislikes from User."

    @property
    def args_schema(self) -> type[BaseModel]:
        return SaveMemoryArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        user_id = context.user_id
        if not user_id:
            return "Error: no user_id in context"
        facts = kwargs["facts"]
        likes = kwargs["likes"]
        dislikes = kwargs["dislikes"]
        existing = (
            await context.services.memory.get_user_memory(user_id)
            if context.services.memory
            else None
        )
        if existing is not None:
            facts = list({*existing.get("facts", ()), *facts})
            likes = list({*existing.get("likes", ()), *likes})
            dislikes = list({*existing.get("dislikes", ()), *dislikes})
        if context.services.memory is not None:
            await context.services.memory.save_user_memory(
                user_id,
                {"facts": facts, "likes": likes, "dislikes": dislikes},
            )
        else:
            return "Error: memory service not available"
        return "Ok"
