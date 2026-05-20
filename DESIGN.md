# Design Document — Multi-Tool Chat Application

## 1. Architecture Overview

The system is a full-stack chat application built around a LangGraph agent that can invoke multiple tools. All persistent state lives in Redis; file uploads use S3-compatible object storage.

```
┌─────────────────────┐   SSE stream   ┌───────────────────────────────────────┐
│  React / Vite SPA   │────-──────────▶│  FastAPI                              │
│  (port 5173)        │                │                                       │
└─────────────────────┘                │  ┌─────────────────────────────────┐  │
                                       │  │  LangGraph Agent Graph          │  │
                                       │  │                                 │  │
                                       │  │  START                          │  │
                                       │  │    │                            │  │
                                       │  │    ▼                            │  │
                                       │  │  cache_lookup ──hit──▶ END      │  │
                                       │  │    │ miss                       │  │
                                       │  │    ▼                            │  │
                                       │  │  agent ◀─────────┐              │  │
                                       │  │    │ tool_calls  │              │  │
                                       │  │    ▼             │              │  │
                                       │  │  tools ──────────┘              │  │
                                       │  │    │ no tool_calls              │  │
                                       │  │    ▼                            │  │
                                       │  │  cache_store ──▶ END            │  │
                                       │  └─────────────────────────────────┘  │
                                       │                                       │
                                       │  Session Manager (record/recall)      │
                                       │  Summarizer sub-agent (map-reduce)    │
                                       └───────────────────────────────────────┘
                                                        │
                              ┌─────────────────────────┼─────────────────┐
                              │                         │                 │
                              ▼                         ▼                 ▼
                           Redis                     S3 / S3-Ninja    PostgreSQL
                  sessions · tool results        file uploads        personal finance
                  LangGraph checkpoints          CSV reads via       (credit_cards,
                  semantic cache                 csv_s3              loans, income,
                  RAG ingestion queue            PDF/doc uploads     expenses, etc.)
                  long-term memory store         for rag_upload      RAG doc chunks
                                                                     (pgvector)
```

### Component Map

| Layer                        | Path                                              | Responsibility                                                                                                                                                                                                                                                                                                                                      |
| ---------------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| HTTP API                     | `backend/src/app/api/routes.py`                   | SSE chat stream, session CRUD, presigned upload URL; all routes protected by `get_current_user` except `/health` and `/config`                                                                                                                                                                                                                      |
| Auth                         | `backend/src/app/auth/jwt.py`                     | `get_current_user` FastAPI dependency — validates RS256 JWT against Keycloak JWKS; `_JWKSCache` caches public keys for 5 min with key-rotation refresh; returns `CurrentUser(sub, username)`                                                                                                                                                        |
| Agent graph                  | `backend/src/app/agent/graph.py`                  | LangGraph state machine, command node, cache nodes, streaming                                                                                                                                                                                                                                                                                       |
| LLM factory                  | `backend/src/app/agent/llm.py`                    | Anthropic / Ollama abstraction                                                                                                                                                                                                                                                                                                                      |
| Summarizer                   | `backend/src/app/agent/summarizer.py`             | Map-reduce sub-agent for oversized tool output                                                                                                                                                                                                                                                                                                      |
| Vectorizer                   | `backend/src/app/agent/vectorizer.py`             | Embedding model for semantic cache                                                                                                                                                                                                                                                                                                                  |
| Session manager              | `backend/src/app/session/manager.py`              | Truncation policy; persists and sizes every tool result                                                                                                                                                                                                                                                                                             |
| Session store                | `backend/src/app/session/store.py`                | `RedisSessionStore` — sessions, payloads, records; sessions indexed by `user:{user_id}:sessions` sets                                                                                                                                                                                                                                               |
| Models                       | `backend/src/app/session/models.py`               | `ToolResultRecord`, `SessionRecord` (includes `user_id` field)                                                                                                                                                                                                                                                                                      |
| Tool kernel                  | `backend/src/app/tools/kernel.py`                 | `ToolKernel` — registers plugins, runs middleware, dispatches `execute_tool()`                                                                                                                                                                                                                                                                      |
| Tool plugin                  | `backend/src/app/tools/plugin.py`                 | `ToolPlugin` ABC, `ToolContext`, `KernelServices`                                                                                                                                                                                                                                                                                                   |
| Tools                        | `backend/src/app/tools/plugins/`                  | `http_fetch`, `csv_s3`, `image_s3`, `sql_query`, `sql_ddl`, `sql_dml`, `weather_api`, `recall`, `save_memory`, `read_memory`, `rag_upload`, `rag_search`, `rag_status`, `rag_list`, `rag_delete`, `doc_preview`                                                                                                                                     |
| Personal finance             | `backend/src/app/tools/plugins/personal_finance/` | 9 thin proxy plugins (`add_credit_card`, `add_loan`, `add_income`, `add_expense`, `get_report`, `list_conflicts`, `payment_to_credit_card`, `payment_to_loan`, `transferred_to_savings`); each calls the corresponding MCP tool at `{FINANCE_SERVICE_URL}/mcp` via `fastmcp.client.Client`; `user_id` injected from `context.user_id`               |
| MCP weather service          | `services/mcp_weather_service/`                   | Standalone FastMCP microservice (port 8002) exposing a `get_weather` MCP tool at `/mcp`; called by `WeatherPlugin` via `fastmcp.client.Client`                                                                                                                                                                                                      |
| MCP documents service        | `services/mcp_documents/`                         | Standalone FastMCP microservice (port 8003) for RAG: `main.py` exposes `rag_upload`, `rag_search`, `rag_queue_status`, `rag_list`, `rag_delete`, `doc_preview` MCP tools; `worker.py` is an async loop that chunks and embeds documents via Ollama and stores vectors in PostgreSQL with pgvector; `rag_queue.py` manages the Redis ingestion queue |
| MCP personal-finance service | `services/mcp_personal_finance/`                  | Standalone FastMCP microservice (port 8004) exposing the 9 personal-finance MCP tools; `db.py` owns the async `asyncpg` pool and runs `CREATE TABLE IF NOT EXISTS` schema init on startup; `config.py` reads `CHAT_APP_URL`                                                                                                                         |
| Upload                       | `backend/src/app/upload/storage_service.py`       | Presigned S3 URL generation; upload keys use `{uuid}-{filename}` format                                                                                                                                                                                                                                                                             |
| Keycloak service             | `keycloak/`                                       | `Dockerfile` builds Keycloakify theme JAR then embeds it in the official Keycloak image; `realm-export.json` defines the `multi-tool-chat` realm and `frontend` OIDC client (public, PKCE); mounted into the container for `--import-realm` on first start                                                                                          |
| Keycloak theme               | `keycloak/keycloakify/`                           | React/Vite/Tailwind custom login page built with Keycloakify; compiled to a `.jar` provider at build time                                                                                                                                                                                                                                           |
| Frontend                     | `frontend/src/`                                   | React + Vite + Tailwind chat UI; `keycloak.ts` holds the `keycloak-js` instance; `api.ts` provides `apiFetch()` which injects `Authorization: Bearer`; `main.tsx` gates app render behind `onLoad: "login-required"`                                                                                                                                |
| Infrastructure               | `infra/`                                          | Terraform modules: network, data (DynamoDB/S3), compute (ECS/ALB/ECR), frontend (CloudFront/S3)                                                                                                                                                                                                                                                     |

---

## 2. Key Technical Decisions

### 2.1 Session Manager Owns the Truncation Policy

Every tool result passes through `ResultProcessor.process()` in `tools/services/result.py`. The kernel dispatches calls through middleware (logging, error handling) before reaching the plugin, then pipes results through the processor.

The decision tree:

```
payload tokens ≤ inline_limit (4 000)  → return full payload inline + store it
payload tokens > inline_limit           → summarize via sub-agent + store it
```

The agent always receives a JSON metadata envelope:

```json
{
  "handle": "tr_abc123def456",
  "tool": "http_fetch",
  "summary": "Page title: ..., 3 paragraphs about ...",
  "token_estimate": 4200,
  "size_bytes": 18432,
  "created_at": "2026-05-06T12:00:00Z"
}
```

For inline results, `result` is added to the envelope. For oversized results, only the summary is present; the agent must call `recall(handle)` to re-materialize the payload. This satisfies the core requirement that the agent uses metadata to decide whether to bring a result back into context.

### 2.2 `recall` Is an Explicit Agent Tool

The agent is not automatically given full payloads — it must issue a `recall(handle)` tool call. This prevents accidental context bloat: the agent reasons from the summary and only recalls when summary is insufficient. The system prompt instructs the agent on this contract explicitly.

### 2.12 Keycloak Authentication and User Scoping

Every API route except `/health` and `/config` is protected by `get_current_user`, a FastAPI dependency in `backend/src/app/auth/jwt.py`.

**Token validation flow:**

1. The frontend (via `keycloak-js`, `onLoad: "login-required"`) redirects the user to Keycloak if no valid session exists.
2. After login, the frontend receives a JWT and silently refreshes it every 60 seconds (`updateToken(30)`).
3. Every API call goes through `apiFetch()` in `frontend/src/api.ts`, which injects `Authorization: Bearer {token}`.
4. `get_current_user` extracts the JWT `kid` header, fetches the matching RS256 public key from Keycloak's JWKS endpoint (cached in `_JWKSCache` for 5 minutes; force-refreshed on key-not-found to handle rotation), and verifies the token signature, issuer, and `azp`/`aud` against `KEYCLOAK_CLIENT_ID`.
5. A `CurrentUser(sub, username)` dataclass is injected into route handlers.

**User scoping:**

- `SessionRecord` stores `user_id = CurrentUser.sub`.
- `RedisSessionStore` indexes sessions under `user:{user_id}:sessions` (a Redis set), so `list_sessions(user_id)` returns only that user's sessions.
- `delete_session` removes the session from the user set and also pipeline-deletes all `payload:{handle}` keys for the session.
- `/sessions/{id}/messages` and `DELETE /sessions` return HTTP 403 if the authenticated user doesn't own the session.
- Tool plugins that are user-scoped (`save_memory`, `read_memory`, all `personal_finance.*` plugins) read `user_id` from `context.user_id` rather than from tool arguments.

**Keycloak service:**

The `keycloak` Docker Compose service runs Keycloak 24 in dev mode (`start-dev --import-realm`), backed by the shared Postgres instance. On first start it imports `keycloak/realm-export.json`, which defines:

- Realm `multi-tool-chat`
- Client `frontend` — public client, PKCE flow, redirect URI `http://localhost:5173/*`

The service image is built from `keycloak/Dockerfile`: a multi-stage build that compiles the Keycloakify React/Tailwind login theme into a `.jar` provider, then copies it into the official Keycloak image.

### 2.9 RAG Pipeline (mcp_documents microservice)

Six tools — `rag_upload`, `rag_search`, `rag_queue_status`, `rag_list`, `rag_delete`, `doc_preview` — delegate to `mcp_documents` (port 8003), a standalone FastMCP service. The pipeline is:

1. **Ingest** — `rag_upload(s3_url)` inserts a document record in PostgreSQL and pushes the `doc_id` onto a Redis list (`rag:queue`). Returns `job_id` and queue position.
2. **Process** — A background `worker_loop()` dequeues jobs, downloads the file from S3, splits it into overlapping text chunks (`chunk_size=1000`, `overlap=200`), embeds each chunk via `POST /api/embed` (Ollama), and writes chunk rows with a `vector(768)` column to a pgvector table.
3. **Search** — `rag_search(query, top_k)` embeds the query with the same Ollama endpoint, runs a cosine-similarity `ORDER BY embedding <=> $1 LIMIT $2` query, and returns ranked chunks with temporary presigned S3 download links for the source documents.
4. **Status** — `rag_queue_status()` returns all documents in `pending` or `processing` state.
5. **List** — `rag_list(search_term, max_documents)` returns all indexed documents with status, chunk count, upload/completion timestamps, original `s3://` URL, and a temporary presigned download link. Supports optional filename filtering and pagination via `has_more`.
6. **Delete** — `rag_delete(s3_url)` removes all chunks for a document from the pgvector table and deletes the S3 object. Documents currently in `processing` state cannot be deleted.
7. **Preview** — `doc_preview(s3_url)` downloads a document from S3 and returns a raw text snippet plus an LLM-generated summary without adding it to the index.

Supported file types: txt, pdf, docx, pptx, xlsx, and images (via the vision model configured in `mcp_documents`). The service is included in Docker Compose and depends on PostgreSQL and Redis. `RAG_SERVICE_URL` configures the endpoint (default `http://localhost:8003`).

Interrupted jobs (status = `processing` at startup) are automatically re-queued via `requeue_interrupted()` in the lifespan handler.

### 2.11 MCP Microservice Tools

Three standalone FastMCP services extend the tool set via the MCP protocol. Each is called by a `ToolPlugin` subclass using `fastmcp.client.Client` with `StreamableHttpTransport`, so the kernel, middleware, and `ResultProcessor` remain unchanged.

**`mcp_weather_service`** (port 8002) — `WeatherPlugin` invokes the `get_weather` MCP tool at `{WEATHER_SERVICE_URL}/mcp`. The service handles geocoding (via open-meteo) and returns current temperature, wind speed, and an hourly forecast. It is a minimal FastMCP app with no FastAPI dependency — only `fastmcp` and `httpx`.

**`mcp_documents`** (port 8003) — `RagUploadPlugin`, `RagSearchPlugin`, `RagStatusPlugin`, `RagListPlugin`, `RagDeletePlugin`, and `DocPreviewPlugin` invoke the corresponding MCP tools at `{RAG_SERVICE_URL}/mcp`. The service manages the full RAG pipeline (see §2.9). Its `main.py` registers all MCP tools and runs a background worker task via a lifespan handler.

**`mcp_personal_finance`** (port 8004) — nine thin proxy plugins under `tools/plugins/personal_finance/` invoke the corresponding MCP tools at `{FINANCE_SERVICE_URL}/mcp`. The service owns the PostgreSQL schema (inline `CREATE TABLE IF NOT EXISTS` on startup) and all DB access, so the backend plugins contain no database logic. The service exposes `add_credit_card`, `add_loan`, `add_income`, `add_expense`, `payment_to_credit_card`, `payment_to_loan`, `get_report`, `list_conflicts`, and `transferred_to_savings`.

This pattern demonstrates that `ToolPlugin` subclasses are provider-agnostic: a plugin can call a local library, a database, a plain REST service, or an MCP server. Docker Compose starts all three services and wires `WEATHER_SERVICE_URL`, `RAG_SERVICE_URL`, and `FINANCE_SERVICE_URL` into the backend environment automatically.

### 2.10 Personal Finance Pipeline (mcp_personal_finance microservice)

Nine tools under the `personal_finance.*` namespace handle budgeting and liability tracking. All database logic lives in `services/mcp_personal_finance/`, a standalone FastMCP service (port 8004). The backend plugins in `tools/plugins/personal_finance/` are thin proxies that forward calls to `{FINANCE_SERVICE_URL}/mcp` via `fastmcp.client.Client` — they contain no database code.

The service's `db.py` owns the async `asyncpg` pool and runs `CREATE TABLE IF NOT EXISTS` schema init on first pool acquisition. Tables: `credit_cards`, `loans`, `income`, `expenses`, `pending_conflicts`, `savings_transfers`.

All tools are scoped by `user_id`, which the agent derives from a prior `/login` call or from memory. Duplicate-entry conflicts are written to `pending_conflicts` rather than silently overwriting existing records, and `list_conflicts` surfaces them for user resolution.

### 2.3 Map-Reduce Summarization Sub-Agent

When a tool result exceeds the inline token limit, `summarizer.summarize()` is called:

- If the payload fits in one 4 000-token chunk: single summarization call.
- Otherwise: each chunk is summarized independently (map), then all partial summaries are reduced in one final call (reduce).

A cheaper/faster model (`claude-haiku-4-5` or `qwen2.5:7b`) is used for both map and reduce steps, keeping latency and cost low.

### 2.4 Redis as the Single Backing Store

All state flows through one Redis instance:

| Key pattern                     | Contents                                                                              |
| ------------------------------- | ------------------------------------------------------------------------------------- |
| `session` (hash)                | Session metadata records (`SessionRecord` JSON, includes `user_id`)                   |
| `user:{user_id}:sessions` (set) | Session IDs belonging to a Keycloak user; populated on session create/delete          |
| `records:{session_id}` (set)    | Handles belonging to a session                                                        |
| `handles` (hash)                | `ToolResultRecord` JSON keyed by handle                                               |
| `payload:{handle}`              | Raw tool output string                                                                |
| LangGraph namespace             | Checkpoint data (managed by `AsyncRedisSaver`)                                        |
| `llm_cache`                     | Semantic cache vectors (managed by `redisvl`)                                         |
| Memory namespace                | Long-term user facts (managed by LangGraph `RedisStore`)                              |
| `rag:queue` (list)              | RAG ingestion queue — `doc_id` UUIDs awaiting processing (managed by `mcp_documents`) |

Choosing Redis as the single store simplifies local development (one `docker compose up`) and eliminates the DynamoDB/S3 dependency that the original infrastructure modules reference. The `USE_AWS_STORE` flag in config preserves the option to switch.

### 2.5 Semantic Cache

A `redisvl.SemanticCache` wraps query/response pairs with vector embeddings. On each chat turn, the cache is checked before the agent is invoked. A cache hit short-circuits the entire graph and returns the stored response immediately, tagged with `source: "CACHE"` in the frontend.

The cache uses the plain prompt as the key (no session-ID prefix), so hits are shared across sessions:

```python
cache.check(prompt=prompt, distance_threshold=0.09)
```

The distance threshold is 0.09, permissive enough to match semantically equivalent rephrasings. Cache entries expire after 5 minutes (TTL = 300 s).

### 2.6 Session-Scoped Context Variable for Tools

The LangGraph graph runs asynchronously, and tool factories receive a `session_id_provider: Callable[[], str]` rather than the session ID itself. The provider reads a `ContextVar` (`_current_session`) that is set via `_bind_session(session_id)` for the duration of each agent invocation. This ensures that concurrent sessions do not share state even within the same process.

### 2.7 Dual LLM Provider Support

`agent/llm.py` provides `build_chat_llm()` and `build_summarizer_llm()` that switch between `langchain_anthropic.ChatAnthropic` and `langchain_ollama.ChatOllama` based on `LLM_PROVIDER`. This allows local development without an API key using Ollama, and cloud deployment using Claude.

### 2.8 Server-Sent Events for Streaming

The `/chat` endpoint returns an `EventSourceResponse`. The backend yields typed events:

| Event type        | Payload                                                                               |
| ----------------- | ------------------------------------------------------------------------------------- |
| `session`         | `{session_id}` — first event, establishes or confirms session                         |
| `token`           | `{content}` — incremental assistant text chunk                                        |
| `reasoning_token` | `{content}` — model reasoning/thinking text                                           |
| `tool_call`       | `{id, name, args}` — agent issued a tool call                                         |
| `tool_result`     | `{tool_call_id, content}` — tool result metadata envelope                             |
| `message`         | `{role, content, source}` — final assistant message                                   |
| `usage`           | `{estimated_tokens, input_tokens, output_tokens}` — token usage after each agent turn |
| `done`            | `{}` — stream complete                                                                |

The frontend assembles these events into the chat item list in `App.tsx`.

---

## 3. Trade-offs

### 3.1 Redis + PostgreSQL: Two Backing Stores

**Redis** holds all transient and conversation-scoped data: sessions, tool-result payloads, LangGraph checkpoints, the semantic cache, long-term memory, and the RAG ingestion queue (`rag:queue`).

**PostgreSQL** holds two datasets: personal finance data (credit cards, loans, income, expenses, savings transfers) and RAG document chunks with pgvector embeddings. Both are structured and relational, making a proper SQL database a better fit than Redis hashes.

**Cost of Redis:** It is an in-memory store. Unbounded payload accumulation causes OOM. There are no TTLs on `payload:{handle}` keys. `delete_session` now pipeline-deletes all `payload:{handle}` keys for the session (previously leaked). A single Redis instance is also a single point of failure.

**Alternative not taken:** DynamoDB + S3 (the infrastructure modules reference this). It would give durable, scalable storage but adds operational complexity and cost for a development prototype.

### 3.2 Semantic Cache Disabled for Recommended Provider

The semantic cache requires a vector embedding API. LangChain's Anthropic integration does not expose an embedding model, so `build_vectorizer_llm()` returns `None` when `LLM_PROVIDER=anthropic`, and the cache nodes are omitted from the graph entirely. Yet `claude-sonnet-4-6` is the recommended and default provider.

In practice, the semantic cache only works when using Ollama with an embedding model such as `embeddinggemma` (the current default) or `nomic-embed-text`.

**Alternative not taken:** Use a third-party embedding provider (e.g. Amazon Titan, Cohere) regardless of the chat LLM. This was not implemented to keep the number of external dependencies low.

### 3.3 Token Estimation Uses OpenAI Tokenizer

`tiktoken.get_encoding("cl100k_base")` (GPT-4's tokenizer) is used to count tokens and decide when to summarize. Claude uses a different tokenizer; estimates can diverge by 10–20%. In practice this means the inline/summarize threshold is approximate, not exact.

**Alternative not taken:** Use Anthropic's `count_tokens` API call. This would add latency on every tool result.

### 3.4 `recall` Bypasses Sizing Limits

The `recall` tool returns the full raw payload directly into the agent's context with no size check. A recalled 1 MB payload fills the context window in a single step. The session manager's truncation policy applies on first storage, not on re-injection.

**Alternative:** Apply the inline limit check to `recall` output as well, returning a second-level summary if the payload is still too large. Not implemented.

### 3.5 Single-Instance Global Graph

The LangGraph graph (`_graph`) and checkpointer (`_checkpointer`) are module-level singletons initialized on first use with an `asyncio.Lock`. This is correct for a single-process deployment but does not scale horizontally without a shared Redis checkpointer (which is already used, so horizontal scaling is actually feasible — but the guard assumes a single writer for the initialization step).

### 3.6 SQL Execution Against an Embedded SQLite Database

`sql_query`, `sql_ddl`, and `sql_dml` all execute against a single in-process SQLite database. There is no per-session isolation: any user can read or mutate any table created by any other user. SQL is validated only by a keyword prefix check (e.g., DDL must start with `CREATE`, `DROP`, or `ALTER`), which is not a sufficient injection defense.

---

## 4. Incomplete Features and Proposed Designs

### 4.1 Token Streaming Not Implemented

**Current state:** The backend emits `token` events, and the frontend accumulates them into a `streaming` bubble. However, the LangGraph `astream` in `graph.py` processes `AIMessageChunk` events but the actual text arrives as a single chunk rather than word-by-word because `max_tokens=2048` is set with no streaming configuration on the Anthropic client.

**Proposed fix:** Pass `streaming=True` to `ChatAnthropic` and use `graph.astream(..., stream_mode=["messages"])` exclusively for token events to get genuine incremental chunks.

### 4.2 Session Title Auto-Generation

**Current state:** All sessions are created with the title `"New Session"` or the first user message text (set in `ensure_session`). There is no LLM-based summarization of the conversation into a title.

**Proposed design:** After the first agent response in a new session, invoke the summarizer LLM with the first user message and generate a 4–6 word title. Write it back with a new `update_session_title` method on `SessionStore`.

### 4.3 Pants Build System Partially Configured

**Current state:** `BUILD` files exist throughout `backend/` and `frontend/`, and `pants.toml` is present. The Pants targets compile and can run tests (`pants test backend/tests::`), but the Docker image target (`pants package backend:api-image`) and the full CI pipeline are not fully wired.

**Proposed fix:** Complete `backend/BUILD` with a `docker_image` target pointing to `Dockerfile`, and add a `pants run` entry point for the FastAPI app.

### 4.4 AWS Terraform Deployment Not Applied

**Current state:** Terraform modules exist for network, compute (ECS Fargate + ALB + ECR), data (DynamoDB + S3), and frontend (CloudFront + S3). No Terraform state file exists; the infrastructure has never been applied.

**Known gaps before applying:**

- No ElastiCache (Redis) resource in any module; the backend expects `REDIS_URL`.
- ALB has HTTP only (no HTTPS listener or ACM certificate).
- ECS tasks placed in public subnets with `assign_public_ip = true`.
- IAM policy on the ECS task role uses `Resource: ["*"]` for DynamoDB.
- ECR repository has `image_tag_mutability = "MUTABLE"`.

**Proposed fixes:**

1. Add an `aws_elasticache_replication_group` resource in the data module.
2. Add HTTPS listener + `aws_acm_certificate` in the compute module.
3. Move ECS tasks to private subnets; add a NAT Gateway in the network module.
4. Scope the DynamoDB IAM policy to specific table ARNs.

### 4.5 Tool Errors Not Surfaced to Agent

**Current state:** Exceptions in tool runners are caught by LangGraph's `ToolNode`, which returns an error string as a `ToolMessage`. However, `make_session_tool()` does not wrap the runner in a try/except before calling `record_tool_result`, so an exception before the payload is generated bypasses the session manager entirely. The agent may receive a raw traceback or an empty result.

**Proposed fix:** Wrap the runner call in `make_session_tool._coro` with a try/except; on failure, call `record_tool_result` with a structured error payload so the session manager still stores the event and the agent sees a consistent envelope.

### 4.6 Authentication and Authorization

**Implemented.** See §2.12. All routes (except `/health` and `/config`) are protected by Keycloak-issued JWTs. Sessions are user-scoped via `user:{user_id}:sessions` Redis sets. Tool plugins (`save_memory`, `read_memory`, all `personal_finance.*`) derive `user_id` from `context.user_id` (the JWT `sub`). Session ownership is enforced on `/sessions/{id}/messages` and `DELETE /sessions`.

**Remaining gap:** The embedded SQLite database (`sql_query`, `sql_ddl`, `sql_dml`) still has no per-user isolation — any authenticated user can read or mutate any table.

### 4.7 Redis Key Cleanup and TTL Policy

**Partially implemented.** `delete_session` now pipeline-deletes all `payload:{handle}` keys for the session (fixed in the Keycloak auth commit). Remaining gaps:

- `payload:{handle}` keys still have no TTL — a session that is never deleted (the common case) accumulates payloads indefinitely.
- LangGraph checkpoint keys have no TTL.

**Proposed remaining fix:**

- Set a TTL (e.g., 7 days) on `payload:{handle}` at write time.
- Add TTLs to LangGraph checkpoint keys via a background cleanup job or by configuring `AsyncRedisSaver` with a retention policy.
