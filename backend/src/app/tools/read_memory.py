from pydantic import BaseModel, Field

from app.memory.store import MemoryStore
from app.tools.base import make_session_tool


class MemoryArgs(BaseModel):
    user_id: str = Field(
        ...,
        description="The name which the user identifies itself, like 'My name is John' for example",
    )


async def _run(user_id: str) -> str:
    try:
        item = await MemoryStore().redis.get(f"users:{user_id}")
        if item is not None:
            return item.decode()
        return "{}"
    except Exception as e:
        return f"Error {e}"


def factory(session_id_provider):
    return make_session_tool(
        name="read_memory",
        description="Read facts, likes and dislikes from User whenever presented",
        args_schema=MemoryArgs,
        runner=_run,
        session_id_provider=session_id_provider,
    )
