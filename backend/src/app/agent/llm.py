"""LLM provider factory.

Switches between Anthropic (production / cloud) and Ollama (local dev,
no API key required) based on `settings.llm_provider`.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from app.config import settings


def build_chat_llm() -> BaseChatModel:
    if settings.llm_provider == "anthropic":
        return _build_antropic(model_name=settings.model_name, tokens=2048)
    elif settings.llm_provider == "ollama":
        return _build_ollama(model_name=settings.ollama_model, reasoning=True)


def build_summarizer_llm() -> BaseChatModel:
    if settings.llm_provider == "anthropic":
        return _build_antropic(model_name=settings.summarizer_model)
    elif settings.llm_provider == "ollama":
        return _build_ollama(model_name=settings.ollama_summarizer_model)


def _build_antropic(model_name: str, tokens: int = 1024) -> BaseChatModel:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty. "
            "Set the key, or switch to LLM_PROVIDER=ollama for local dev."
        )
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model_name,
        api_key=settings.anthropic_api_key,
        max_tokens=tokens,
        temperature=0,
    )


def _build_ollama(model_name: str, reasoning: bool = False) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=model_name,
        base_url=settings.ollama_base_url,
        temperature=0,
        reasoning=reasoning,
    )
