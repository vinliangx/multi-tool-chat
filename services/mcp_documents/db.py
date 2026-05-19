from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import numpy as np
from config import settings
from pgvector.asyncpg import register_vector

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
        await conn.execute("""
            ALTER TABLE rag.chunks ADD COLUMN IF NOT EXISTS ts_content tsvector
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS rag_chunks_ts_idx
            ON rag.chunks USING gin(ts_content)
        """)


async def insert_document(doc_id: uuid.UUID, s3_url: str, filename: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO rag.documents (id, s3_url, filename, status) VALUES ($1, $2, $3, 'pending')",
            doc_id,
            s3_url,
            filename,
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
                status,
                chunk_count,
                doc_id,
            )
        elif status == "failed":
            await conn.execute(
                "UPDATE rag.documents SET status=$1, error=$2 WHERE id=$3",
                status,
                error,
                doc_id,
            )
        else:
            await conn.execute(
                "UPDATE rag.documents SET status=$1 WHERE id=$2",
                status,
                doc_id,
            )


async def insert_chunks(
    doc_id: uuid.UUID,
    chunks: list[str],
    embeddings: list[list[float]],
    metadata_list: list[dict] | None = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        for i, (text, emb) in enumerate(zip(chunks, embeddings)):
            meta = metadata_list[i] if metadata_list else {}
            await conn.execute(
                "INSERT INTO rag.chunks"
                " (id, document_id, content, embedding, chunk_index, metadata, ts_content)"
                " VALUES ($1, $2, $3, $4, $5, $6, to_tsvector('english', $3))",
                uuid.uuid4(),
                doc_id,
                text,
                np.array(emb, dtype=np.float32),
                i,
                json.dumps(meta),
            )


async def search_chunks(
    query_embedding: list[float],
    query_text: str,
    top_k: int,
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    pool = await get_pool()
    fetch_k = top_k * 4
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH vector_ranked AS (
                SELECT c.id,
                       ROW_NUMBER() OVER (ORDER BY c.embedding <=> $1) AS rank
                FROM rag.chunks c
                JOIN rag.documents d ON d.id = c.document_id
                WHERE d.status = 'completed'
                  AND 1 - (c.embedding <=> $1) >= $3
                LIMIT $2
            ),
            bm25_ranked AS (
                SELECT c.id,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank_cd(c.ts_content,
                                               plainto_tsquery('english', $4)) DESC
                       ) AS rank
                FROM rag.chunks c
                JOIN rag.documents d ON d.id = c.document_id
                WHERE d.status = 'completed'
                  AND c.ts_content @@ plainto_tsquery('english', $4)
                LIMIT $2
            ),
            combined AS (
                SELECT COALESCE(v.id, b.id) AS id,
                       COALESCE(1.0 / (60 + v.rank), 0.0)
                     + COALESCE(1.0 / (60 + b.rank), 0.0) AS rrf_score
                FROM vector_ranked v
                FULL OUTER JOIN bm25_ranked b ON v.id = b.id
            )
            SELECT c.content,
                   d.id::text AS document_id,
                   d.s3_url,
                   d.filename,
                   cm.rrf_score AS score,
                   c.metadata
            FROM combined cm
            JOIN rag.chunks c ON c.id = cm.id
            JOIN rag.documents d ON d.id = c.document_id
            ORDER BY cm.rrf_score DESC
            LIMIT $5
            """,
            np.array(query_embedding, dtype=np.float32),
            fetch_k,
            min_score,
            query_text,
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


async def get_all_documents(
    search_term: str | None = None, limit: int = 21
) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if search_term:
            rows = await conn.fetch(
                """
                SELECT id::text, s3_url, filename, status, created_at, completed_at, error, chunk_count
                FROM rag.documents
                WHERE filename ILIKE $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                f"%{search_term}%",
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id::text, s3_url, filename, status, created_at, completed_at, error, chunk_count
                FROM rag.documents
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [dict(r) for r in rows]


async def delete_document_by_s3_url(s3_url: str) -> dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, s3_url, filename, status, chunk_count FROM rag.documents WHERE s3_url = $1",
            s3_url,
        )
        if not row:
            return {"error": f"No document found with s3_url: {s3_url}"}
        if row["status"] == "processing":
            return {"error": f"Document '{row['filename']}' is currently processing. Try again once it completes."}
        doc_id = row["id"]
        await conn.execute("DELETE FROM rag.chunks WHERE document_id = $1", doc_id)
        await conn.execute("DELETE FROM rag.documents WHERE id = $1", doc_id)
        return {
            "deleted": True,
            "doc_id": str(doc_id),
            "filename": row["filename"],
            "s3_url": row["s3_url"],
            "chunks_removed": row["chunk_count"] or 0,
        }


async def get_queue_status() -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id::text, s3_url, filename, status, created_at
            FROM rag.documents
            WHERE status IN ('pending', 'processing','completed')
            ORDER BY created_at
            """
        )
        return [dict(r) for r in rows]
