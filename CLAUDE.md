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
3. `kernel.bind_context(session_id)` sets the `ContextVar` so all plugins see the current session
4. The LangGraph graph in `agent/graph.py` loops: Agent node (LLM) → Tool node → back to Agent until done
5. Each tool call dispatches through `ToolKernel.execute_tool()`: middleware → plugin → `ResultProcessor`
6. Events stream back: `session`, `token`, `tool_call`, `tool_result`, `chunk_progress`, `done`

### Tool truncation policy (critical pattern)

Every tool result passes through `ResultProcessor.process()` in `tools/services/result.py`:

- ≤4,000 tokens → returned inline to the agent
- >4,000 tokens → summarized, then `{handle, summary, token_estimate, ...}` returned (map-reduce for very large payloads)

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
- **Tool execution context** is threaded via `ContextVar` (`_current_context` / `_current_session`). Plugins access the current session and services through `ToolContext`, set by `kernel.bind_context()` before each request.
- **Cycle detection** — `ToolKernel` tracks in-flight tools per-request via a `ContextVar[frozenset]`; re-entering the same tool raises `ToolCycleError`.
- Tests use `monkeypatch` to replace `summarize()` and a `reset_store` fixture to clear in-memory state between tests.
