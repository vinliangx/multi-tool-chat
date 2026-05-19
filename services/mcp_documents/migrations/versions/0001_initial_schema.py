"""Initial RAG schema: rag.documents, rag.chunks, HNSW + GIN indexes

Revision ID: 3f8a21c04b7d
Revises:
Create Date: 2026-05-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "3f8a21c04b7d"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _embedding_dimensions() -> int:
    from config import settings

    return settings.embedding_dimensions


def upgrade() -> None:
    dims = _embedding_dimensions()

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS rag")

    op.execute("""
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

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS rag.chunks (
            id           UUID PRIMARY KEY,
            document_id  UUID NOT NULL REFERENCES rag.documents(id),
            content      TEXT NOT NULL,
            embedding    vector({dims}),
            chunk_index  INT NOT NULL,
            metadata     JSONB,
            ts_content   tsvector
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
        ON rag.chunks USING hnsw (embedding vector_cosine_ops)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS rag_chunks_ts_idx
        ON rag.chunks USING gin(ts_content)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS rag_chunks_ts_idx")
    op.execute("DROP INDEX IF EXISTS rag_chunks_embedding_idx")
    op.execute("DROP TABLE IF EXISTS rag.chunks")
    op.execute("DROP TABLE IF EXISTS rag.documents")
    op.execute("DROP SCHEMA IF EXISTS rag")
