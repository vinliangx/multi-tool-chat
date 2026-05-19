# RAG Production Gaps

Roughly 30-40% of the way to production. Right architectural bones, but significant gaps remain.

## What's genuinely good

- Correct stack choices: pgvector + HNSW index, asyncpg, Redis queue with crash-recovery requeue on startup, async worker, MCP microservice separation
- Document variety: PDF/docx/pptx/xlsx/txt/images all handled
- Vision fallback: LLM image description for non-text files is a real production pattern
- `rag_delete` cleans up both index and S3 — many implementations leave orphaned data

## TODOs

### Chunking quality (biggest retrieval impact)

`chunker.py` is purely character-based — splits on byte offsets with no awareness of words, sentences, or paragraphs. Chunks frequently start/end mid-word or mid-sentence, which meaningfully degrades embedding quality.

- [x] Replace with sentence-aware or semantic chunking (e.g., LangChain's `RecursiveCharacterTextSplitter`, `chonkie`, or `llama-index` node parsers)

### Retrieval quality

- [x] **Hybrid search** — layer BM25 (`tsvector`) alongside vector search to handle keyword-heavy queries (e.g., "find the contract dated 2024-03-15")
- [x] **Reranking** — apply a cross-encoder (Cohere Rerank, `cross-encoder/ms-marco-*`) after initial retrieval; this is table stakes at production
- [x] **Score threshold** — filter out low-similarity results; currently 0.4 and 0.9 cosine similarity results are returned with no relevance floor signal
- [x] **Parent-chunk retrieval** — use small chunks for search, large chunks for context; populate the `metadata` column (currently always `{}`)

### Reliability

- [ ] **Concurrency** — single worker processes one doc at a time; add a parallelism setting
- [ ] **Retry for failed docs** — failed docs stay permanently unusable; a transient Ollama timeout should be retryable
- [ ] **Deduplication** — uploading the same `s3_url` twice silently creates duplicate index entries
- [ ] **Batch embeddings** — `worker.py:143` fires one HTTP request per chunk via `asyncio.gather`; Ollama's `/api/embed` supports batching

### Embedding provider

- [ ] Abstract embedding behind a provider-agnostic interface — currently locked to Ollama even when `LLM_PROVIDER=anthropic`; support OpenAI, Cohere, Voyage, etc.

### Schema management

- [x] Replace `CREATE TABLE IF NOT EXISTS` in `db.py:34` with proper Alembic migrations — changes need to be versioned, auditable, and reversible

### Auth / multi-tenancy

- [ ] Scope `rag.documents` by `user_id` or `session_id` — currently all documents are globally shared; any session can search or delete any other session's documents
