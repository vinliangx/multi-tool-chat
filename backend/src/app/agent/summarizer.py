"""Summarization sub-agent.

Used by the session manager whenever a tool result exceeds the inline
token limit. For results that exceed the summarize limit, we map-reduce:
chunk -> summarize each chunk -> summarize the summaries.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.agent.llm import build_summarizer_llm

# Set to an asyncio.Queue by run_agent_stream so progress events can be
# interleaved into the SSE stream while the graph is blocked in ToolNode.
_progress_queue: ContextVar[asyncio.Queue | None] = ContextVar(
    "summarizer_progress", default=None
)


_SYSTEM = (
    "You compress tool output for an AI agent's context window. "
    "Preserve concrete facts, numbers, identifiers, and any errors. "
    "You have to hold necessary information to answer counting questions."
    "Drop boilerplate. Be terse. The agent can request the full payload "
    "later via a recall handle if it needs raw detail."
)


def _llm():
    return build_summarizer_llm()


def _chunk(text: str, target_tokens: int = 4000) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=target_tokens,
        chunk_overlap=target_tokens * 0.1,
        add_start_index=True,
        separators=["\n\n", "\n", " ", ""],
    )

    chunks = splitter.split_text(text)
    return chunks


async def summarize(
    payload: str,
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    target_tokens: int = 400,
) -> str:
    chunks = _chunk(payload, target_tokens=target_tokens)
    llm = _llm()
    queue = _progress_queue.get()

    if len(chunks) == 1:
        prompt = (
            f"Tool: {tool_name}\nArgs: {tool_args}\n\n"
            f"Output:\n{chunks[0]}\n\n"
            f"Summarize in <= {target_tokens} tokens."
        )
        resp = await llm.ainvoke(
            [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
        )
        return str(resp.content)

    partials: list[str] = []
    for idx, chunk in enumerate(chunks):
        prompt = (
            f"Tool: {tool_name} (chunk {idx + 1}/{len(chunks)})\n\n"
            f"{chunk}\n\nSummarize this chunk."
        )
        resp = await llm.ainvoke(
            [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
        )
        partials.append(str(resp.content))
        if queue is not None:
            await queue.put(
                (
                    "progress",
                    {
                        "type": "summarize_progress",
                        "data": {
                            "tool_name": tool_name,
                            "current": idx + 1,
                            "total": len(chunks),
                        },
                    },
                )
            )

    reduce_prompt = (
        f"Tool: {tool_name}\nArgs: {tool_args}\n\n"
        f"Per-chunk summaries:\n\n"
        + "\n\n---\n\n".join(partials)
        + f"\n\nProduce one unified summary in <= {target_tokens} tokens."
    )
    resp = await llm.ainvoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=reduce_prompt)]
    )
    return str(resp.content)
