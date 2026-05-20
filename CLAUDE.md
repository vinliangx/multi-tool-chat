# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r 3rdparty/requirements.txt
PYTHONPATH=src uvicorn app.main:app --reload --port 8000
```

Run tests (requires Pants build tool):

```bash
pants test backend/tests::
```

Run a single test file without Pants:

```bash
cd backend
PYTHONPATH=src pytest tests/test_session_manager.py -v
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # TypeScript compile + Vite build
```

### Full Stack (Docker)

```bash
cp .env.example .env   # set LLM_PROVIDER, ANTHROPIC_API_KEY, etc.
docker compose up --build
```

## Architecture

This is a full-stack AI chat app: **React/Vite frontend** → **FastAPI backend** → **LangGraph agent** → **Redis**.

### Authentication

All API routes except `/health` and `/config` require a JWT Bearer token issued by Keycloak.

- **Backend** — `backend/src/app/auth/jwt.py`: `get_current_user` FastAPI dependency. Validates RS256 JWT against Keycloak's JWKS endpoint (`KEYCLOAK_INTERNAL_URL/realms/{realm}/protocol/openid-connect/certs`). Keys are cached for 5 minutes with automatic force-refresh on unknown `kid`. Returns `CurrentUser(sub, username)`.
- **Frontend** — `frontend/src/keycloak.ts`: `keycloak-js` instance. `main.tsx` calls `keycloak.init({ onLoad: "login-required" })` — the app never renders until authenticated. `api.ts` exports `apiFetch()` which calls `keycloak.updateToken(10)` then injects `Authorization: Bearer {token}`. Token is silently refreshed every 60 seconds.
- **Session scoping** — `RedisSessionStore` stores `user_id` on `SessionRecord` and indexes sessions under `user:{user_id}:sessions` (Redis set). `list_sessions(user_id)` returns only that user's sessions.
- **Tool scoping** — `save_memory`, `read_memory`, and all `personal_finance.*` plugins read `user_id` from `context.user_id` (set by the route from the JWT `sub`), not from tool arguments.

### Request flow

1. Browser authenticates via Keycloak; `keycloak-js` obtains a JWT
2. Frontend POSTs to `/chat` with `Authorization: Bearer {token}` and consumes the SSE stream
3. `api/routes.py` validates the token via `get_current_user`, creates/reuses a session (scoped to `current_user.sub`), and calls `run_agent_stream()`
4. `kernel.bind_context(session_id)` sets the `ContextVar` so all plugins see the current session
5. The LangGraph graph in `agent/graph.py`: cache_lookup (Ollama only) → Agent node (LLM) → Tool node → back to Agent until done; responses are stored in cache_store after the final agent turn
6. Each tool call dispatches through `ToolKernel.execute_tool()`: middleware → plugin → `ResultProcessor`
7. Events stream back: `session`, `token`, `reasoning_token`, `tool_call`, `tool_result`, `message`, `usage`, `done`

### Tool truncation policy (critical pattern)

Every tool result passes through `ResultProcessor.process()` in `tools/services/result.py`:

- ≤4,000 tokens → returned inline to the agent
- > 4,000 tokens → summarized, then `{handle, summary, token_estimate, ...}` returned (map-reduce for very large payloads)

The agent can call the `recall(handle)` tool to retrieve the full payload when needed.

### Micro kernel architecture

Tools are organized as a plugin system (`tools/`):

- **`ToolKernel`** — registers plugins, runs middleware, dispatches `execute_tool()`, builds LangChain tools via `build_langchain_tools()`
- **`ToolPlugin`** (ABC) — base class for every tool; subclasses live in `tools/plugins/`
- **`KernelServices`** — container injected into `ToolContext`: `result`, `storage`, `event_bus`, `memory`, `cache`, `metrics`
- **`ToolMiddleware`** — `LoggingMiddleware` and `ErrorHandlingMiddleware` wrap every call
- **`create_kernel()`** in `tools/__init__.py` — wires services, registers `ALL_PLUGINS`, returns a ready kernel

### Adding a new tool

All tools are `ToolPlugin` subclasses in `tools/plugins/`:

```python
from pydantic import BaseModel, Field
from app.tools.plugin import ToolContext, ToolPlugin

class MyArgs(BaseModel):
    arg: str = Field(..., description="...")

class MyPlugin(ToolPlugin):
    @property
    def name(self) -> str: return "my_tool"

    @property
    def description(self) -> str: return "What this tool does"

    @property
    def args_schema(self) -> type[BaseModel]: return MyArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        # context.services gives access to storage, memory, event_bus, etc.
        return "result string"
```

Register the instance in `tools/plugins/__init__.py` by appending it to `ALL_PLUGINS`. The `ToolKernel` automatically runs results through `ResultProcessor` (truncation/summarization) unless `skip_result_processing = True`.

### Personal finance pipeline

Nine tools delegate to `mcp_personal_finance` (port 8004), a standalone FastMCP microservice:

- **`personal_finance.add_credit_card`** — upserts a credit card by `(user_id, name)`.
- **`personal_finance.add_loan`** — upserts a loan by `(user_id, name)`.
- **`personal_finance.add_income`** — records income with duplicate detection; `force=true` overrides.
- **`personal_finance.add_expense`** — records an expense with duplicate detection; `force=true` overrides.
- **`personal_finance.payment_to_credit_card`** — reduces a card's balance.
- **`personal_finance.payment_to_loan`** — reduces a loan's balance.
- **`personal_finance.get_report`** — monthly financial summary (burn rate, daily budget, CC/loan/savings snapshot).
- **`personal_finance.list_conflicts`** — shows pending duplicate conflicts.
- **`personal_finance.transferred_to_savings`** — records a savings transfer.

Each backend plugin in `tools/plugins/personal_finance/` is a thin proxy that calls the corresponding MCP tool at `{FINANCE_SERVICE_URL}/mcp`. The service owns the Postgres schema (inline `CREATE TABLE IF NOT EXISTS` on startup) and runs on port 8004. `FINANCE_SERVICE_URL` defaults to `http://localhost:8004`.

### RAG pipeline

Six tools delegate to `mcp_documents` (port 8003), a standalone FastMCP microservice:

- **`rag_upload(s3_url)`** — inserts a document record in PostgreSQL and pushes `doc_id` onto the Redis ingestion queue. Supported formats: txt, pdf, docx, pptx, xlsx, images.
- **`rag_search(query, top_k)`** — embeds the query via Ollama, runs a cosine-similarity pgvector query, returns ranked chunks with presigned S3 links.
- **`rag_queue_status()`** — returns documents in `pending` or `processing` state.
- **`rag_list(search_term, max_documents)`** — lists all indexed documents with status, chunk count, timestamps, original `s3://` URL, and presigned download links. Supports filename filtering and pagination via `has_more`.
- **`rag_delete(s3_url)`** — removes all chunks for a document from pgvector and deletes the S3 object. Use the original `s3://` URL from `rag_list` output.
- **`doc_preview(s3_url)`** — downloads a document from S3 and returns a raw text snippet plus an LLM-generated summary without indexing.

Each plugin calls the corresponding MCP tool at `{RAG_SERVICE_URL}/mcp` using `fastmcp.client.Client`. A background worker in `services/mcp_documents/worker.py` dequeues jobs, chunks, embeds, and stores vectors in PostgreSQL. `RAG_SERVICE_URL` defaults to `http://localhost:8003`.

### Redis as single backing store

- Session metadata + message history
- Tool result payloads (keyed by handle)
- LangGraph checkpoints
- Semantic cache (Ollama only — disabled for Anthropic)
- Long-term memory (`save_memory`/`read_memory`)
- RAG ingestion queue (`rag:queue` list, managed by `mcp_documents`)

`USE_AWS_STORE=1` switches sessions/payloads to DynamoDB+S3.

### Frontend state

No Redux/Zustand — plain `useState` in `App.tsx`. `items[]` holds all chat messages and tool calls in order. Bubble components (`BubbleUser`, `BubbleAssistant`, `BubbleTool`, `BubbleReasoning`) are pure presentation; `ChatBox` owns input state.

The Vite dev proxy forwards `/chat`, `/sessions`, `/health`, `/upload_url`, `/config` to `http://backend:8000`.

## Key env vars

| Variable                  | Purpose                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| `LLM_PROVIDER`            | `anthropic` (default) or `ollama`                                        |
| `ANTHROPIC_API_KEY`       | Required when `LLM_PROVIDER=anthropic`                                   |
| `MODEL_NAME`              | Main LLM (default: `claude-sonnet-4-6`)                                  |
| `SUMMARIZER_MODEL`        | Summarizer LLM (default: `claude-haiku-4-5-20251001`)                    |
| `REDIS_URL`               | Redis connection (default: `redis://localhost:6379`)                     |
| `OLLAMA_BASE_URL`         | Ollama server URL                                                        |
| `RAG_SERVICE_URL`         | MCP documents / RAG service (default: `http://localhost:8003`)           |
| `KEYCLOAK_EXTERNAL_URL`   | Keycloak URL for the browser (default: `http://localhost:8080`)          |
| `KEYCLOAK_INTERNAL_URL`   | Keycloak URL for the backend container (default: `http://keycloak:8080`) |
| `KEYCLOAK_REALM`          | Keycloak realm (default: `multi-tool-chat`)                              |
| `KEYCLOAK_CLIENT_ID`      | OIDC client ID (default: `frontend`)                                     |
| `VITE_KEYCLOAK_URL`       | Keycloak URL for Vite frontend (default: `http://localhost:8080`)        |
| `VITE_KEYCLOAK_REALM`     | Keycloak realm for Vite frontend                                         |
| `VITE_KEYCLOAK_CLIENT_ID` | OIDC client ID for Vite frontend                                         |

Full list in README.md.

## Notable constraints

- **Semantic cache requires Ollama** — silently disabled when `LLM_PROVIDER=anthropic` because LangChain has no Anthropic embedding API.
- **Token counting** uses `tiktoken` with `cl100k_base` encoding throughout.
- **Summarizer** defaults to Haiku/small Ollama model for cost efficiency; it runs as a sub-agent, not within the main LangGraph graph.
- **Tool execution context** is threaded via `ContextVar` (`_current_context` / `_current_session`). Plugins access the current session, `user_id`, and services through `ToolContext`, set by `kernel.bind_context()` before each request.
- **User ID in tools** — user-scoped plugins (`save_memory`, `read_memory`, all `personal_finance.*`) use `context.user_id` (the JWT `sub`), not a tool argument. Never pass `user_id` as an explicit tool arg for these.
- **Cycle detection** — `ToolKernel` tracks in-flight tools per-request via a `ContextVar[frozenset]`; re-entering the same tool raises `ToolCycleError`.
- **LLM instance caching** — `agent/llm.py` caches `ChatAnthropic`/`ChatOllama` instances keyed by `(model, max_tokens, reasoning)`; instances are reused across requests rather than reconstructed each time.
- **PDF image fallback** — in `mcp_documents`, if text extraction from a PDF page fails, the worker falls back to the vision model for that page.
- Tests use `monkeypatch` to replace `summarize()` and a `reset_store` fixture to clear in-memory state between tests.
