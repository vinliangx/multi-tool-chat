import asyncio
from typing import List

from langchain_ollama import OllamaEmbeddings
from redisvl.utils.vectorize import CustomTextVectorizer

from app.config import settings


def create_ollama_vectorizer():
    ollama_embedder = OllamaEmbeddings(
        base_url=settings.ollama_base_url, model=settings.ollama_embedding_model
    )

    def sync_embed(text: str) -> List[float]:
        return ollama_embedder.embed_query(text)

    def sync_embed_many(texts: List[str]) -> List[List[float]]:
        return ollama_embedder.embed_documents(texts)

    async def async_embed(text: str) -> List[float]:
        return await asyncio.to_thread(sync_embed, text)

    async def async_embed_many(texts: List[str]) -> List[List[float]]:
        return await asyncio.to_thread(sync_embed_many, texts)

    return CustomTextVectorizer(
        embed=sync_embed,
        aembed=async_embed,
        embed_many=sync_embed_many,
        aembed_many=async_embed_many,
    )


def build_vectorizer_llm() -> CustomTextVectorizer | None:
    if settings.llm_provider == "ollama":
        return create_ollama_vectorizer()
    # Anthropic has no first-party embedding API; semantic cache is disabled.
    return None
