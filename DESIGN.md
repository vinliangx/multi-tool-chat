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
                              ┌─────────────────────────┤
                              │                         │
                              ▼                         ▼
                           Redis                     S3 / S3-Ninja
                  sessions · tool results        file uploads
                  LangGraph checkpoints          CSV reads via csv_s3
                  semantic cache
                  long-term memory store
```

### Component Map

| Layer           | Path                                        | Responsibility                                                                                                   |
| --------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| HTTP API        | `backend/src/app/api/routes.py`             | SSE chat stream, session CRUD, presigned upload URL                                                              |
| Agent graph     | `backend/src/app/agent/graph.py`            | LangGraph state machine, cache nodes, streaming                                                                  |
| LLM factory     | `backend/src/app/agent/llm.py`              | Anthropic / Ollama abstraction                                                                                   |
| Summarizer      | `backend/src/app/agent/summarizer.py`       | Map-reduce sub-agent for oversized tool output                                                                   |
| Vectorizer      | `backend/src/app/agent/vectorizer.py`       | Embedding model for semantic cache                                                                               |
| Session manager | `backend/src/app/session/manager.py`        | Truncation policy; persists and sizes every tool result                                                          |
| Session store   | `backend/src/app/session/store.py`          | `RedisSessionStore` — sessions, payloads, records                                                                |
| Models          | `backend/src/app/session/models.py`         | `ToolResultRecord`, `SessionRecord`                                                                              |
| Tool base       | `backend/src/app/tools/base.py`             | `make_session_tool()` — wraps any runner through the session manager                                             |
| Tools           | `backend/src/app/tools/`                    | `http_fetch`, `csv_s3`, `sql_query`, `sql_ddl`, `sql_dml`, `weather_api`, `recall`, `save_memory`, `read_memory` |
| Upload          | `backend/src/app/upload/storage_service.py` | Presigned S3 URL generation                                                                                      |
| Frontend        | `frontend/src/`                             | React + Vite + Tailwind chat UI with SSE consumer                                                                |
| Infrastructure  | `infra/`                                    | Terraform modules: network, data (DynamoDB/S3), compute (ECS/ALB/ECR), frontend (CloudFront/S3)                  |

---

## 2. Key Technical Decisions

### 2.1 Session Manager Owns the Truncation Policy

Every tool is wrapped by `make_session_tool()` (`tools/base.py`). After a tool's runner produces its raw string payload, it unconditionally calls `record_tool_result` in `session/manager.py` before returning anything to the agent.

The decision tree in `record_tool_result`:

```
payload tokens ≤ inline_limit (1 500)  → return full payload inline + store it
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

### 2.3 Map-Reduce Summarization Sub-Agent

When a tool result exceeds the inline token limit, `summarizer.summarize()` is called:

- If the payload fits in one 4 000-token chunk: single summarization call.
- Otherwise: each chunk is summarized independently (map), then all partial summaries are reduced in one final call (reduce).

A cheaper/faster model (`claude-haiku-4-5` or `qwen2.5:7b`) is used for both map and reduce steps, keeping latency and cost low.

### 2.4 Redis as the Single Backing Store

All state flows through one Redis instance:

| Key pattern                  | Contents                                                 |
| ---------------------------- | -------------------------------------------------------- |
| `session` (hash)             | Session metadata records                                 |
| `records:{session_id}` (set) | Handles belonging to a session                           |
| `handles` (hash)             | `ToolResultRecord` JSON keyed by handle                  |
| `payload:{handle}`           | Raw tool output string                                   |
| LangGraph namespace          | Checkpoint data (managed by `AsyncRedisSaver`)           |
| `llm_cache`                  | Semantic cache vectors (managed by `redisvl`)            |
| Memory namespace             | Long-term user facts (managed by LangGraph `RedisStore`) |

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

| Event type        | Payload                                                       |
| ----------------- | ------------------------------------------------------------- |
| `session`         | `{session_id}` — first event, establishes or confirms session |
| `token`           | `{content}` — incremental assistant text chunk                |
| `reasoning_token` | `{content}` — model reasoning/thinking text                   |
| `tool_call`       | `{id, name, args}` — agent issued a tool call                 |
| `tool_result`     | `{tool_call_id, content}` — tool result metadata envelope     |
| `message`         | `{role, content, source}` — final assistant message           |
| `done`            | `{}` — stream complete                                        |

The frontend assembles these events into the chat item list in `App.tsx`.

---

## 3. Trade-offs

### 3.1 Redis as Single Store: Simplicity vs. Durability and Scale

**Benefit:** Zero additional infrastructure for local dev; a single connection pool; easy to inspect with `redis-cli`.

**Cost:** Redis is an in-memory store. Unbounded payload accumulation causes OOM. There are no TTLs on `payload:{handle}` keys. Deleting a session leaks payload keys (the `delete_session` path removes the session hash and records set, but not the payload keys — a known bug). A single Redis instance is also a single point of failure.

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

**Current state:** No authentication. Any client that can reach the API can read, modify, or delete any session. Memory is keyed by a user-supplied string, allowing User A to overwrite User B's memory.

**Proposed design:** Add JWT-based auth middleware in FastAPI. Derive a `user_id` from the token. Scope all session, tool-result, and memory keys by `user_id`. Add a session ownership check on every session endpoint.

### 4.7 Redis Key Cleanup and TTL Policy

**Current state:** `payload:{handle}` keys are never expired. `delete_session` does not delete payload keys. Over time, Redis memory grows without bound.

**Proposed fix:**

- Set a TTL (e.g., 7 days) on `payload:{handle}` at write time.
- In `delete_session`, pipeline-delete all `payload:{handle}` keys for the session in the same transaction.
- Add TTLs to LangGraph checkpoint keys via a background cleanup job or by configuring `AsyncRedisSaver` with a retention policy.
