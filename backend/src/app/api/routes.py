import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import (
    cache,
    delete_session_checkpoints,
    get_session_messages,
    run_agent_stream,
)
from app.auth.jwt import CurrentUser, get_current_user
from app.config import settings
from app.session.models import SessionRecord
from app.session.store import get_store
from app.upload.storage_service import UploadRequest, get_upload_url

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    files: list[dict] | None = None


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config")
async def get_config() -> dict:
    return {"context_window_token_limit": settings.context_window_token_limit}


@router.delete("/cache")
async def clear_cache(
    _: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    if cache is not None:
        cache.clear()
    return {"status": "ok"}


@router.get("/sessions")
async def list_session(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[SessionRecord]:
    return await get_store().list_sessions(current_user.sub)


@router.post("/sessions")
async def create_session(
    title: str = "New Session",
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    sid = str(uuid.uuid4())
    await get_store().create_session(sid, title, current_user.sub)
    return {"session_id": sid}


@router.delete("/sessions")
async def delete_session(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    session = await get_store().get_session(session_id)
    if session is not None and session.user_id and session.user_id != current_user.sub:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    await get_store().delete_session(session_id=session_id)
    await delete_session_checkpoints(session_id)


@router.get("/sessions/{session_id}/messages")
async def session_messages(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    session = await get_store().get_session(session_id)
    if session is not None and session.user_id and session.user_id != current_user.sub:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    messages = await get_session_messages(session_id)
    items: list[dict] = []
    tool_item_indices: dict[str, int] = {}

    for msg in messages:
        if isinstance(msg, HumanMessage):
            items.append({"kind": "user", "text": str(msg.content)})
        elif isinstance(msg, AIMessage):
            if "reasoning_content" in msg.additional_kwargs:
                items.append(
                    {
                        "kind": "reasoning_token",
                        "text": str(msg.additional_kwargs["reasoning_content"]),
                        "source": (
                            "LLM"
                            if msg.response_metadata.get("model_name")
                            else "CACHE"
                        ),
                    }
                )
            for tc in msg.tool_calls or []:
                tool_item_indices[tc["id"]] = len(items)
                items.append(
                    {
                        "kind": "tool",
                        "call": {
                            "id": tc["id"],
                            "name": tc["name"],
                            "args": tc["args"],
                        },
                    }
                )

            if msg.content:
                items.append(
                    {
                        "kind": "assistant",
                        "text": str(msg.content),
                        "source": (
                            "LLM"
                            if msg.response_metadata.get("model_name")
                            else "CACHE"
                        ),
                    }
                )

        elif isinstance(msg, ToolMessage):
            idx = tool_item_indices.get(msg.tool_call_id)
            if idx is not None:
                items[idx]["call"]["result"] = json.dumps(msg.content)

    return items


@router.post("/chat")
async def chat(
    req: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    session_id = req.session_id or str(uuid.uuid4())
    store = get_store()
    await store.ensure_session(session_id, req.message, current_user.sub)

    async def event_stream():
        yield {"event": "session", "data": json.dumps({"session_id": session_id})}
        async for event in run_agent_stream(session_id, req.message, req.files, current_user.sub):
            yield {"event": event["type"], "data": json.dumps(event["data"])}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_stream())


@router.post("/upload_url")
async def upload_url(
    req: UploadRequest,
    _: CurrentUser = Depends(get_current_user),
):
    return get_upload_url(req=req)
