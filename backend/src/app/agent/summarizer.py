"""Summarization sub-agent.

Used by the session manager whenever a tool result exceeds the inline
token limit. For results that exceed the summarize limit, we map-reduce:
chunk -> summarize each chunk -> summarize the summaries.
"""

from __future__ import annotations

from typing import Any

import tiktoken
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import build_summarizer_llm

_enc = tiktoken.get_encoding("cl100k_base")

_SYSTEM = (
    "You compress tool output for an AI agent's context window. "
    "Preserve concrete facts, numbers, identifiers, and any errors. "
    "Drop boilerplate. Be terse. The agent can request the full payload "
    "later via a recall handle if it needs raw detail."
)


def _llm():
    return build_summarizer_llm()


def _chunk(text: str, target_tokens: int = 4000) -> list[str]:
    tokens = _enc.encode(text)
    if len(tokens) <= target_tokens:
        return [text]
    return [
        _enc.decode(tokens[i : i + target_tokens])
        for i in range(0, len(tokens), target_tokens)
    ]


async def summarize(
    payload: str,
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    target_tokens: int = 400,
) -> str:
    chunks = _chunk(payload)
    llm = _llm()

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
