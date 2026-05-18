# RAG Implementation Plan

## Service: `services/mcp_documents` (port 8003)

Standalone FastMCP microservice that chunks, embeds, and indexes documents from S3
into pgvector, with a Redis-backed persistent job queue and a background worker.

---

## Infrastructure changes

### `docker-compose.yml`
- Change `postgres` image: `postgres:16-alpine` → `pgvector/pgvector:pg16` (data-compatible)
- Add `mcp_documents` service wired to postgres, redis, s3
- Add `RAG_SERVICE_URL: http://mcp_documents:8003` to `backend` environment
- Add `mcp_documents` to backend `depends_on`

### New env vars
| Var | Default | Purpose |
|-----|---------|---------|
| `VISION_MODEL` | `claude-sonnet-4-6` | Model for image description |
| `VISION_PROVIDER` | `anthropic` | `anthropic` or `ollama` |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `EMBEDDING_DIMENSIONS` | `768` | Vector dimensions (must match model) |
| `RAG_SERVICE_URL` | `http://localhost:8003` | Backend → mcp_documents URL |
| `RAG_DB_URL` | (same as POSTGRES_URL) | pgvector connection string |

---

## `services/mcp_documents/` file layout

```
services/mcp_documents/
├── Dockerfile          python:3.12-slim, runs main.py
├── requirements.txt    fastmcp, asyncpg, pgvector, redis, boto3,
│                       PyMuPDF, python-docx, python-pptx, openpyxl,
│                       httpx, pydantic-settings, anthropic, numpy
├── config.py           pydantic-settings for all env vars
├── db.py               asyncpg pool, schema init, CRUD, vector search
├── rag_queue.py        Redis queue: enqueue / dequeue / requeue_interrupted
├── chunker.py          fixed-size chunking (1000 chars / 200 overlap)
├── worker.py           asyncio background loop: download → extract → embed → store
└── main.py             FastMCP app, lifespan, 3 tools, health endpoint
```

---

## Database schema (rag schema in existing finance_db)

Created on startup via `CREATE IF NOT EXISTS`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA  IF NOT EXISTS rag;

CREATE TABLE rag.documents (
    id           UUID PRIMARY KEY,
    s3_url       TEXT NOT NULL,
    filename     TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | completed | failed
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error        TEXT,
    chunk_count  INT
);

CREATE TABLE rag.chunks (
    id           UUID PRIMARY KEY,
    document_id  UUID NOT NULL REFERENCES rag.documents(id),
    content      TEXT NOT NULL,
    embedding    vector(768),        -- dim from EMBEDDING_DIMENSIONS
    chunk_index  INT NOT NULL,
    metadata     JSONB
);

CREATE INDEX rag_chunks_embedding_idx ON rag.chunks USING hnsw (embedding vector_cosine_ops);
```

---

## Queue design (Redis-backed, DB as source of truth)

| Operation | Redis command | DB action |
|-----------|--------------|-----------|
| Enqueue | `RPUSH rag:queue <id>` | INSERT status=pending |
| Dequeue | `BLPOP rag:queue` | UPDATE status=processing |
| Complete | — (nothing in Redis) | UPDATE status=completed |
| Fail | — | UPDATE status=failed |
| Restart recovery | `RPUSH` for any pending/processing rows not in queue | — |

On startup: re-push any DB rows with `status IN ('pending','processing')` to Redis queue
(handles interrupted jobs after container restart).

---

## MCP tools (in `main.py`)

| Tool name | Args | Returns |
|-----------|------|---------|
| `rag_upload` | `s3_url: str` | `{job_id, filename, position_in_queue}` |
| `rag_queue_status` | — | `[{job_id, s3_url, filename, status, created_at}]` |
| `rag_search` | `query: str, top_k: int=5` | `[{content, score, filename, s3_url (presigned 1h)}]` |

---

## Document type handling (worker)

| Extensions | Extraction method |
|-----------|------------------|
| `.txt .md .csv .json .xml .html` | UTF-8 decode |
| `.pdf` | PyMuPDF (`fitz.open`) |
| `.docx` | python-docx |
| `.pptx` | python-pptx (iterate shapes) |
| `.xlsx .xls` | openpyxl (rows → pipe-delimited) |
| `.png .jpg .jpeg .gif .webp .bmp` | VISION_MODEL → text description |

---

## Backend bridge plugins (separate files per action)

```
backend/src/app/tools/plugins/
├── rag_upload.py    RagUploadPlugin   name="rag_upload"
├── rag_search.py    RagSearchPlugin   name="rag_search"
└── rag_status.py    RagStatusPlugin   name="rag_queue_status"
```

All follow the `WeatherPlugin` pattern: `StreamableHttpTransport` → `Client.call_tool()`.
Registered in `tools/plugins/__init__.py`.

---

## Files to create (12) / modify (2)

**Create:**
- `services/mcp_documents/{Dockerfile, requirements.txt, config.py, db.py, rag_queue.py, chunker.py, worker.py, main.py}`
- `backend/src/app/tools/plugins/{rag_upload.py, rag_search.py, rag_status.py}`

**Modify:**
- `docker-compose.yml` — new service + postgres image + backend env
- `backend/src/app/tools/plugins/__init__.py` — register 3 new plugins
