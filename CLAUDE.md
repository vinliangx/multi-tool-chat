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

### Request flow

1. Frontend POSTs to `/chat` and consumes the SSE stream
2. `api/routes.py` creates/reuses a session and calls `run_agent_stream()`
3. The LangGraph graph in `agent/graph.py` loops: Agent node (LLM) → Tool node → back to Agent until done
4. Each tool is wrapped by `make_session_tool()` → `record_tool_result()`, which applies the truncation policy (see below)
5. Events stream back: `session`, `token`, `tool_call`, `tool_result`, `chunk_progress`, `done`

### Tool truncation policy (critical pattern)

Every tool result passes through `record_tool_result()` in `session/manager.py`:

- ≤4,000 tokens → returned inline to the agent
- 4,000–8,000 tokens → summarized, then `{handle, summary, token_estimate, ...}` returned
- > 8,000 tokens → chunked via `RecursiveCharacterTextSplitter`, map-reduce summarized

The agent can call the `recall(handle)` tool to retrieve the full payload when needed.

### Adding a new tool

All tools follow the factory pattern in `tools/`:

```python
def factory(session_id_provider: Callable[[], str]) -> StructuredTool:
    async def _run(arg: str, ...) -> str:
        return await record_tool_result(session_id_provider(), "tool_name", {...}, result)
    return make_session_tool("tool_name", "description", ArgsSchema, _run, session_id_provider)
```

Register the factory in `tools/registry.py`.

### Redis as single backing store

- Session metadata + message history
- Tool result payloads (keyed by handle)
- LangGraph checkpoints
- Semantic cache (Ollama only — disabled for Anthropic)
- Long-term memory (`save_memory`/`read_memory`)

`USE_AWS_STORE=1` switches sessions/payloads to DynamoDB+S3.

### Frontend state

No Redux/Zustand — plain `useState` in `App.tsx`. `items[]` holds all chat messages and tool calls in order. Bubble components (`BubbleUser`, `BubbleAssistant`, `BubbleTool`, `BubbleReasoning`) are pure presentation; `ChatBox` owns input state.

The Vite dev proxy forwards `/chat`, `/sessions`, `/health`, `/upload_url`, `/config` to `http://backend:8000`.

## Key env vars

| Variable            | Purpose                                               |
| ------------------- | ----------------------------------------------------- |
| `LLM_PROVIDER`      | `anthropic` (default) or `ollama`                     |
| `ANTHROPIC_API_KEY` | Required when `LLM_PROVIDER=anthropic`                |
| `MODEL_NAME`        | Main LLM (default: `claude-sonnet-4-6`)               |
| `SUMMARIZER_MODEL`  | Summarizer LLM (default: `claude-haiku-4-5-20251001`) |
| `REDIS_URL`         | Redis connection (default: `redis://localhost:6379`)  |
| `OLLAMA_BASE_URL`   | Ollama server URL                                     |

Full list in README.md.

## Notable constraints

- **Semantic cache requires Ollama** — silently disabled when `LLM_PROVIDER=anthropic` because LangChain has no Anthropic embedding API.
- **Token counting** uses `tiktoken` with `cl100k_base` encoding throughout.
- **Summarizer** defaults to Haiku/small Ollama model for cost efficiency; it runs as a sub-agent, not within the main LangGraph graph.
- **Session ID threading** uses a `ContextVar` (`_current_session`) rather than explicit parameter passing — tools access the current session via a `session_id_provider` callable.
- Tests use `monkeypatch` to replace `summarize()` and a `reset_store` fixture to clear in-memory state between tests.
