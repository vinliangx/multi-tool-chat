from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector

from config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async def _init(conn: asyncpg.Connection) -> None:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await register_vector(conn)

        _pool = await asyncpg.create_pool(settings.rag_db_url, init=_init)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS rag")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rag.documents (
                id           UUID PRIMARY KEY,
                s3_url       TEXT NOT NULL,
                filename     TEXT,
                status       TEXT NOT NULL DEFAULT 'pending',
                created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                error        TEXT,
                chunk_count  INT
            )
        """)
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS rag.chunks (
                id           UUID PRIMARY KEY,
                document_id  UUID NOT NULL REFERENCES rag.documents(id),
                content      TEXT NOT NULL,
                embedding    vector({settings.embedding_dimensions}),
                chunk_index  INT NOT NULL,
                metadata     JSONB
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
            ON rag.chunks USING hnsw (embedding vector_cosine_ops)
        """)


async def insert_document(doc_id: uuid.UUID, s3_url: str, filename: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO rag.documents (id, s3_url, filename, status) VALUES ($1, $2, $3, 'pending')",
            doc_id, s3_url, filename,
        )


async def update_document_status(
    doc_id: uuid.UUID,
    status: str,
    error: str | None = None,
    chunk_count: int | None = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status == "completed":
            await conn.execute(
                "UPDATE rag.documents SET status=$1, completed_at=NOW(), chunk_count=$2 WHERE id=$3",
                status, chunk_count, doc_id,
            )
        elif status == "failed":
            await conn.execute(
                "UPDATE rag.documents SET status=$1, error=$2 WHERE id=$3",
                status, error, doc_id,
            )
        else:
            await conn.execute(
                "UPDATE rag.documents SET status=$1 WHERE id=$2",
                status, doc_id,
            )


async def insert_chunks(
    doc_id: uuid.UUID,
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        for i, (text, emb) in enumerate(zip(chunks, embeddings)):
            await conn.execute(
                "INSERT INTO rag.chunks (id, document_id, content, embedding, chunk_index, metadata)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                uuid.uuid4(),
                doc_id,
                text,
                np.array(emb, dtype=np.float32),
                i,
                json.dumps({}),
            )


async def search_chunks(query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.content,
                   d.id::text      AS document_id,
                   d.s3_url,
                   d.filename,
                   1 - (c.embedding <=> $1) AS score
            FROM rag.chunks c
            JOIN rag.documents d ON d.id = c.document_id
            WHERE d.status = 'completed'
            ORDER BY c.embedding <=> $1
            LIMIT $2
            """,
            np.array(query_embedding, dtype=np.float32),
            top_k,
        )
        return [dict(r) for r in rows]


async def get_pending_documents() -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, s3_url FROM rag.documents"
            " WHERE status IN ('pending', 'processing') ORDER BY created_at"
        )
        return [dict(r) for r in rows]


async def get_queue_status() -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id::text, s3_url, filename, status, created_at
            FROM rag.documents
            WHERE status IN ('pending', 'processing')
            ORDER BY created_at
            """
        )
        return [dict(r) for r in rows]
