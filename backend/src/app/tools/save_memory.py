import json

from pydantic import BaseModel, Field

from app.memory.store import MemoryStore
from app.tools.base import make_session_tool


class MemoryArgs(BaseModel):
    user_id: str = Field(..., description="The name of the user in lowercase")
    facts: list[str] = Field(
        ..., description="List of facts of the user, besides his/her name"
    )
    likes: list[str] = Field(..., description="List of likes")
    dislikes: list[str] = Field(..., description="List of dislikes")


async def _run(
    user_id: str,
    facts: list[str],
    likes: list[str],
    dislikes: list[str],
) -> str:
    try:
        existing = await MemoryStore().redis.get(f"users:{user_id}")
        if existing is not None:
            old = json.loads(existing.decode())
            facts = list({*old.get("facts", ()), *facts})
            likes = list({*old.get("likes", ()), *likes})
            dislikes = list({*old.get("dislikes", ()), *dislikes})
        await MemoryStore().redis.set(
            f"users:{user_id}",
            json.dumps({"facts": facts, "likes": likes, "dislikes": dislikes}),
        )
    except Exception as e:
        return f"Error {e}"
    return "Ok"


def factory(session_id_provider):
    return make_session_tool(
        name="save_memory",
        description="Store facts, likes and dislikes from User.",
        args_schema=MemoryArgs,
        runner=_run,
        session_id_provider=session_id_provider,
    )
