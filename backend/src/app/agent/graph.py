"""LangGraph agent.

Flow:
  start -> agent -> (tools? -> agent) -> end

The summarizer is *not* a node here — it's invoked from inside the
session manager whenever a tool result is too large. That keeps the
graph simple and the summarization transparent to the agent: every
tool result it ever sees is already context-budget-friendly, with a
recall handle if it wants the raw bytes.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, AsyncIterator, Literal, TypedDict

import tiktoken
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.redis import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from redisvl.extensions.cache.llm import SemanticCache

from app.agent.llm import build_chat_llm
from app.agent.summarizer import _progress_queue as _summarizer_progress_queue
from app.agent.vectorizer import build_vectorizer_llm
from app.config import settings
from app.tools import create_kernel

_enc = tiktoken.get_encoding("cl100k_base")


def _estimate_tokens(messages: list[AnyMessage]) -> int:
    total = 0
    for m in messages:
        content = m.content
        if isinstance(content, str):
            total += len(_enc.encode(content))
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total += len(_enc.encode(part["text"]))
    return total


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    cached: bool
    last_usage: dict


_kernel = create_kernel()
_LLM: BaseChatModel | None = None
_TOOLS: list[BaseTool] = []
_VECTORIZER = build_vectorizer_llm()  # None when provider has no embedding API

_SYSTEM = SystemMessage(
    content=(
        "You are a helpful and polite assistant with access to tools. "
        "You explain things briefly and to the point."
        "Tool results are returned as JSON metadata: {handle, tool, summary, ...}. "
        "If the summary is enough, answer from it. "
        "If you need the full raw output, call the `recall` tool with the handle. "
        "Any destructive action requires confirmation, before calling any tool. "
        "IMPORTANT: Always call `read_memory` before calling `save_memory` so you "
        "can merge existing facts, likes, and dislikes with any new information. "
        "Dont `save_memory` if nothing has change, compare before calling the tool."
        "If nothing exists from this user, save it, and ask more questions about facts, likes or dislikes"
    )
)


cache: SemanticCache | None = (
    SemanticCache(
        name="llm_cache",
        redis_url=settings.redis_url,
        distance_threshold=0.09,
        vectorizer=_VECTORIZER,
        ttl=5 * 60,
    )
    if _VECTORIZER is not None
    else None
)


def _inject_file_urls(messages: list[AnyMessage]) -> list[AnyMessage]:
    out = []
    for msg in messages:
        files = (
            msg.additional_kwargs.get("files")
            if isinstance(msg, HumanMessage)
            else None
        )
        if files:
            file_lines = "\n".join(f"- {f['name']}: {f['url']}" for f in files)
            msg = HumanMessage(
                content=f"{msg.content}\n\nAttached files (use these URLs with tools):\n{file_lines}",
            )
        out.append(msg)
    return out


async def _agent_node(state: AgentState) -> dict:
    msgs = [_SYSTEM, *_inject_file_urls(state["messages"])]
    estimated = _estimate_tokens(msgs)
    if estimated > settings.context_window_token_limit:
        msgs = trim_messages(
            msgs,
            max_tokens=settings.context_window_token_limit,
            strategy="last",
            token_counter=_estimate_tokens,
            include_system=True,
            allow_partial=False,
            start_on="human",
        )
        estimated = _estimate_tokens(msgs)
    resp = await _LLM.ainvoke(msgs)
    usage = resp.usage_metadata or {}
    return {
        "messages": [resp],
        "last_usage": {
            "estimated_tokens": estimated,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        },
    }


def _route_after_agent(state: AgentState) -> Literal["tools", "cache_store"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "cache_store"


def _route_after_agent_no_cache(state: AgentState) -> Literal["tools"] | str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def _cache_lookup_node(state: AgentState):
    prompt = state["messages"][-1].content
    cached = cache.check(prompt=f"{prompt}", distance_threshold=0.09)
    if cached:
        return {
            "messages": [
                AIMessage(
                    content=cached[0]["response"],
                )
            ],
            "cached": True,
        }
    return {"cached": False}


def _cache_store_node(state: AgentState):
    messages = state["messages"]

    prompt = None
    assistant_msg = None

    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.tool_calls:
            break
        elif isinstance(m, AIMessage) and not m.tool_calls:
            assistant_msg = m.content
        elif isinstance(m, HumanMessage):
            prompt = m.content
        if prompt and assistant_msg:
            break

    if not prompt or not assistant_msg:
        return {}
    cache.store(prompt=f"{prompt}", response=assistant_msg)
    return {}


def _route_after_cache(state: AgentState):
    if state.get("cached"):
        return END
    return "agent"


def _build_graph(checkpointer: BaseCheckpointSaver):
    g = StateGraph(AgentState)
    g.add_node("agent", _agent_node)
    g.add_node("tools", ToolNode(_TOOLS))
    g.add_edge("tools", "agent")

    if cache is not None:
        g.add_edge(START, "cache_lookup")
        g.add_node("cache_lookup", _cache_lookup_node)
        g.add_node("cache_store", _cache_store_node)

        g.add_conditional_edges(
            "cache_lookup", _route_after_cache, {END: END, "agent": "agent"}
        )
        g.add_conditional_edges(
            "agent",
            _route_after_agent,
            {"tools": "tools", "cache_store": "cache_store"},
        )
        g.add_edge("cache_store", END)
    else:
        g.add_edge(START, "agent")
        g.add_conditional_edges(
            "agent", _route_after_agent_no_cache, {"tools": "tools", END: END}
        )

    return g.compile(checkpointer=checkpointer)


_graph = None
_checkpointer: AsyncRedisSaver | None = None
_graph_lock = asyncio.Lock()


async def _get_graph():
    global _graph, _checkpointer, _TOOLS, _LLM
    if _graph is None:
        async with _graph_lock:
            if _graph is None:
                await _kernel.init()
                _TOOLS = _kernel.build_langchain_tools()
                _LLM = build_chat_llm().bind_tools(_TOOLS)
                _checkpointer = AsyncRedisSaver(redis_url=settings.redis_url)
                await _checkpointer.asetup()
                _graph = _build_graph(_checkpointer)
    return _graph


async def delete_session_checkpoints(session_id: str) -> None:
    """Remove all LangGraph checkpoint data for a session."""
    await _get_graph()
    if _checkpointer is not None:
        await _checkpointer.adelete_thread(session_id)


async def get_session_messages(session_id: str) -> list[AnyMessage]:
    """Return the full message history for a session from the LangGraph checkpoint."""
    await _get_graph()
    config = {"configurable": {"thread_id": session_id}}
    checkpoint_tuple = await _checkpointer.aget_tuple(config)
    if checkpoint_tuple is None:
        return []
    return checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages", [])


async def run_agent_stream(
    session_id: str, user_message: str, files: list[dict] | None
) -> AsyncIterator[dict]:
    """Yield events from a single chat turn.

    Event types:
      token              — incremental assistant text
      tool_call          — agent invoked a tool {name, args, id}
      tool_result        — tool's session-manager view {name, view}
      summarize_progress — chunk progress while summarizing a large result
      message            — final assistant message
    """
    initial: AgentState = {
        "messages": [
            HumanMessage(
                content=user_message,
                additional_kwargs={"files": files} if files else {},
            )
        ],
    }
    config = {"configurable": {"thread_id": session_id}}

    graph = await _get_graph()

    # Shared queue: graph events are fed by a background task; the summarizer
    # (running inside ToolNode) puts progress events directly via ContextVar.
    event_queue: asyncio.Queue = asyncio.Queue()
    progress_token = _summarizer_progress_queue.set(event_queue)

    async def _feed():
        try:
            with _kernel.bind_context(session_id):
                async for stream_type, event in graph.astream(
                    initial,
                    stream_mode=["updates", "messages"],
                    config=config,
                ):
                    await event_queue.put(("graph", stream_type, event))
        except Exception as exc:
            await event_queue.put(("error", exc))
            return
        await event_queue.put(("done", None))

    feed_task = asyncio.create_task(_feed())

    def _process_graph_event(stream_type: str, event):
        """Convert a raw graph event into zero or more yield-able dicts."""
        out = []
        if stream_type == "messages":
            msg_chunk, metadata = event
            if (
                isinstance(msg_chunk, AIMessageChunk)
                and isinstance(msg_chunk.content, str)
                and msg_chunk.content
                and metadata.get("langgraph_node") == "agent"
            ):
                out.append({"type": "token", "data": {"content": msg_chunk.content}})
            elif (
                isinstance(msg_chunk, AIMessageChunk)
                and isinstance(msg_chunk.content, str)
                and "reasoning_content" in msg_chunk.additional_kwargs
            ):
                out.append(
                    {
                        "type": "reasoning_token",
                        "data": {
                            "content": msg_chunk.additional_kwargs["reasoning_content"]
                        },
                    }
                )
        elif stream_type == "updates":
            for node_name, update in event.items():
                if update is not None:
                    for msg in update.get("messages", []):
                        if isinstance(msg, AIMessage):
                            for tc in msg.tool_calls or []:
                                out.append(
                                    {
                                        "type": "tool_call",
                                        "data": {
                                            "id": tc["id"],
                                            "name": tc["name"],
                                            "args": tc["args"],
                                        },
                                    }
                                )
                            if msg.content:
                                out.append(
                                    {
                                        "type": "message",
                                        "data": {
                                            "role": "assistant",
                                            "content": msg.content,
                                            "source": "CACHE"
                                            if node_name == "cache_lookup"
                                            else "LLM",
                                        },
                                    }
                                )
                        elif isinstance(msg, ToolMessage):
                            out.append(
                                {
                                    "type": "tool_result",
                                    "data": {
                                        "tool_call_id": msg.tool_call_id,
                                        "content": msg.content,
                                    },
                                }
                            )
                if node_name == "agent" and update.get("last_usage"):
                    out.append({"type": "usage", "data": update["last_usage"]})
        return out

    try:
        while True:
            item = await event_queue.get()
            kind = item[0]
            if kind == "done":
                break
            elif kind == "error":
                raise item[1]
            elif kind == "progress":
                yield item[1]
            else:  # "graph"
                _, stream_type, event = item
                for evt in _process_graph_event(stream_type, event):
                    yield evt
    finally:
        _summarizer_progress_queue.reset(progress_token)
        if not feed_task.done():
            feed_task.cancel()
            try:
                await feed_task
            except asyncio.CancelledError:
                pass
