# Multi-Tool Chat Application

Full-stack chat application where a LangGraph agent invokes multiple tools, with a Session Manager that persists tool results and a summarization sub-agent for oversized output.

## Architecture

```
┌────────────┐  SSE  ┌───────────────────────────────┐
│ React/Vite │──────▶│ FastAPI + LangGraph           │
└────────────┘       │  ┌──────────────┐             │
                     │  │CommandsNode  │             │
                     │  │ /login /tools│             │
                     │  └──────┬───────┘             │
                     │         ▼                     │
                     │  ┌──────────────┐             │
                     │  │SemanticCache │◀──────────┐ │
                     │  └──────┬───────┘           │ │
                     │         ▼                   │ │
                     │  ┌──────────────┐           │ │
                     │  │ Agent (LLM)  │◀─┐        │ │
                     │  └──────┬───────┘  │        │ │
                     │         ▼          │        │ │
                     │  ┌──────────────┐  │        │ │
                     │  │  Tool Node   │──┘        │ │
                     │  │  http_fetch  │           │ │
                     │  │  csv_s3      │           │ │
                     │  │  image_read  │           │ │
                     │  │  sql_query   │           │ │
                     │  │  sql_ddl     │           │ │
                     │  │  sql_dml     │           │ │
                     │  │  weather     │           │ │
                     │  │  recall      │           │ │
                     │  │  save_memory │           │ │
                     │  │  read_memory │           │ │
                     │  │  personal_finance.*      │ │
                     │  └──────┬───────┘           │ │
                     │         ▼                   │ │
                     │  ┌──────────────┐           │ │
                     │  │SessionManager│           │ │
                     │  └──────┬───────┘           │ │
                     └─────────┼───────────────────┘─┘
                               ▼
                             Redis
                     (sessions, tool results,
                      LangGraph checkpoints,
                      semantic cache, memory store)
                               ▲
                               │ summarize when oversized
                           ┌───┴────────┐
                           │ Summarizer │ (Haiku / Ollama, map-reduce)
                           └────────────┘

                           ┌────────────┐
                           │ S3 / Ninja │  (file uploads, csv_s3 reads)
                           └────────────┘

                           ┌────────────┐
                           │ PostgreSQL │  (personal finance data)
                           └────────────┘

                           ┌──────────────────────┐
                           │ MCP Weather Service  │  (weather tool → POST /weather)
                           └──────────────────────┘
```

Key design choices:

- **Micro kernel architecture.** Tools are `ToolPlugin` subclasses registered with `ToolKernel`. The kernel dispatches calls through `ToolMiddleware` (logging, error handling) before reaching the plugin, then pipes results through `ResultProcessor` for truncation/summarization. Adding a new tool means subclassing `ToolPlugin` and appending to `ALL_PLUGINS`.
- **`ResultProcessor` owns the truncation policy.** Every tool routes its output through `ResultProcessor.process()`. Results ≤4,000 tokens are returned inline; oversized results are summarized and persisted, with only `{handle, summary, size, ...}` returned to the agent.
- **`recall(handle)` is an explicit tool.** The agent decides when to bring full content back. This satisfies the requirement: "use metadata from stored results to decide whether a result should be brought back into the context window."
- **Summarizer is map-reduce.** Truly large payloads are chunked via `RecursiveCharacterTextSplitter`, summarized per chunk, then reduced. Progress events are streamed to the UI during summarization.
- **Semantic cache.** Redis-backed `SemanticCache` with vector embeddings de-duplicates repeated queries across sessions (shared cache, distance threshold 0.09, 5-minute TTL), returning cached responses without hitting the LLM. Requires Ollama (`LLM_PROVIDER=ollama`) — silently disabled when using Anthropic because Anthropic has no first-party embedding API in LangChain.
- **Redis is the single backing store.** Session metadata, tool-result payloads, LangGraph checkpoints, the semantic cache, and the long-term memory store all live in Redis — no DynamoDB required.
- **Long-term memory tools.** `save_memory` and `read_memory` persist user facts, likes, and dislikes across sessions via Redis.
- **Vision LLM.** A dedicated vision model (Anthropic or Ollama) handles image analysis. The `image_read` tool reads an image from S3, base64-encodes it, and sends it to the vision LLM with a user prompt — OCR is supported.
- **Context usage tracking.** The agent estimates token usage via `tiktoken` and exposes it through `/config`. A `ContextUsageBadge` in the UI shows current vs. limit tokens in real time.
- **Command node.** A `commands_node` at graph entry intercepts slash commands before routing to the agent or cache. `/login <user_id>` triggers a `read_memory` lookup; `/tools` asks the agent to list available tools. All other input routes normally.
- **Personal finance suite.** Nine tools under the `personal_finance.*` namespace track credit cards, loans, income, expenses, savings transfers, and monthly reports. Finance data is persisted in PostgreSQL (separate from Redis) via an async `asyncpg` connection pool with auto-migration on first use.
- **MCP microservice tool.** The `weather` plugin delegates to an external `mcp_weather_service` FastAPI microservice (port 8002) rather than calling open-meteo directly. It demonstrates how `ToolPlugin` subclasses can call remote HTTP services rather than implementing logic locally; the service is included in Docker Compose and reachable via `WEATHER_SERVICE_URL`.

## Layout

```
backend/        Python (FastAPI + LangGraph), Pants targets
  src/app/
    api/        HTTP routes (SSE chat stream, session CRUD, upload_url)
    agent/      LangGraph graph, summarizer, semantic cache, vectorizer
    session/    Session store + models (RedisSessionStore)
    tools/
      kernel.py     ToolKernel — orchestrates plugins + middleware
      plugin.py     ToolPlugin ABC, ToolContext, KernelServices
      middleware.py LoggingMiddleware, ErrorHandlingMiddleware
      plugins/      One file per tool (http_fetch, csv_s3, image_s3,
                    sql_query, sql_ddl, sql_dml, weather_api,
                    recall, save_memory, read_memory)
                    personal_finance/ (add_credit_card, add_loan,
                    add_income, add_expense, get_report,
                    list_conflicts, payment_to_credit_card,
                    payment_to_loan, transferred_to_savings, db)
      services/     ResultProcessor, StorageService, EventBus,
                    MemoryService, CacheService, MetricsService
    upload/     Presigned S3 URL generation
  tests/
  Dockerfile
frontend/       React + Vite + TS chat UI
  src/
    components/ NavSideBar, Header, ChatBox, FileUpload, FileItem,
                BubbleUser, BubbleAssistant, BubbleTool, BubbleReasoning,
                ChatLoadingIndicator, ConfirmDialog, ContextUsageBadge
services/
  mcp_weather_service/  Standalone FastAPI microservice exposing POST /weather
infra/          Terraform (network, data, compute, frontend modules)
pants.toml
```

## Run locally with Docker

The whole stack — backend, frontend, Redis, and S3 Ninja — runs in Docker:

```bash
cp .env.example .env
docker compose up --build
open http://localhost:5173
```

Use Ollama for local inference:

```bash
# Point to a running Ollama instance (native install recommended on Apple Silicon)
OLLAMA_BASE_URL=http://host.docker.internal:11434 docker compose up
```

Switch to Claude instead of Ollama:

```bash
# in .env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

**Apple Silicon note** — Ollama in Docker on macOS runs CPU-only (no Metal passthrough). For faster inference, install Ollama natively (`brew install ollama && ollama serve`) and set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env`.

**Tool-calling reliability with local models** — small models occasionally miss tool calls or emit malformed args. Ranked best to worst for this app:

1. `qwen2.5:7b` (default — solid tool calling)
2. `llama3.1:8b`
3. `mistral-nemo`

## Local development (without Docker)

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r 3rdparty/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export REDIS_URL=redis://localhost:6379
PYTHONPATH=src uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
```

Tests (via Pants):

```bash
pants test backend/tests::
```

## Deploy to AWS

```bash
# 1. Provision infra (creates ECR, ECS, ALB, CloudFront, ElastiCache Redis)
cd infra/envs/dev
terraform init
terraform apply -var="anthropic_api_key=$ANTHROPIC_API_KEY"

# 2. Build & push images to ECR
ECR=$(terraform output -raw ecr_repo)
ECR_WEATHER=$(terraform output -raw ecr_weather_service)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR
docker build -t $ECR:latest ../../../backend
docker push $ECR:latest
docker build -t $ECR_WEATHER:latest ../../../services/mcp_weather_service
docker push $ECR_WEATHER:latest
aws ecs update-service --cluster mtc-dev-cluster --service mtc-dev-api --force-new-deployment

# 3. Build & upload frontend
cd ../../../frontend
npm run build
SITE=$(cd ../infra/envs/dev && terraform output -raw frontend_url)
aws s3 sync dist/ s3://mtc-dev-frontend/
```

(With Pants: `pants package backend:api-image` builds the image; tag and push it to the ECR URL above.)

## Required env (backend)

| Variable                                     | Purpose                                                                                                                                  |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `LLM_PROVIDER`                               | `anthropic` (default) or `ollama`                                                                                                        |
| `ANTHROPIC_API_KEY`                          | LLM access when `LLM_PROVIDER=anthropic`                                                                                                 |
| `MODEL_NAME`                                 | Override main LLM (default: `claude-sonnet-4-6`)                                                                                         |
| `SUMMARIZER_MODEL`                           | Override summarizer (default: `claude-haiku-4-5-20251001`)                                                                               |
| `OLLAMA_BASE_URL`                            | Ollama server URL (default: `http://localhost:11434`)                                                                                    |
| `OLLAMA_MODEL`                               | Ollama chat model (default: `qwen2.5:7b`)                                                                                                |
| `OLLAMA_SUMMARIZER_MODEL`                    | Ollama summarizer model                                                                                                                  |
| `OLLAMA_EMBEDDING_MODEL`                     | Ollama embedding model for semantic cache (default: `embeddinggemma`)                                                                    |
| `OLLAMA_VISION_MODEL`                        | Ollama vision model (default: `qwen3-vl:latest`)                                                                                         |
| `REDIS_URL`                                  | Redis connection string (default: `redis://localhost:6379`)                                                                              |
| `POSTGRES_URL`                               | PostgreSQL connection string for personal finance data (default: `postgresql://finance_user:finance_password@localhost:5432/finance_db`) |
| `POSTGRES_PASSWORD`                          | PostgreSQL password (used by Docker Compose, default: `finance_password`)                                                                |
| `EXTERNAL_S3_ENDPOINT_URL`                   | S3 endpoint reachable from the browser (presigned URLs)                                                                                  |
| `INTERNAL_S3_ENDPOINT_URL`                   | S3 endpoint reachable from the backend container                                                                                         |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | S3 credentials                                                                                                                           |
| `BUCKET_NAME`                                | S3 bucket for file uploads                                                                                                               |
| `USE_AWS_STORE`                              | `1` to use DynamoDB+S3 for session/tool-result storage (unset = Redis)                                                                   |
| `WEATHER_SERVICE_URL`                        | URL for the MCP weather microservice (default: `http://localhost:8002`)                                                                  |

## Tool reference

| Tool                                      | Description                                                                             |
| ----------------------------------------- | --------------------------------------------------------------------------------------- |
| `http_fetch`                              | Fetch a URL and return the response body                                                |
| `csv_s3`                                  | Read a CSV file from S3; supports `filter_column`/`filter_value` for full-dataset scans |
| `image_read`                              | Read an image from S3 and analyze it with the vision LLM; OCR supported                 |
| `sql_query`                               | Run a SELECT query against the local SQLite DB                                          |
| `sql_ddl`                                 | Run CREATE / DROP / ALTER TABLE statements                                              |
| `sql_dml`                                 | Run INSERT / UPDATE / DELETE statements                                                 |
| `weather`                                 | Get current weather for a location via the MCP weather microservice                     |
| `recall`                                  | Retrieve a full tool-result payload by handle                                           |
| `save_memory`                             | Persist user facts, likes, and dislikes across sessions                                 |
| `read_memory`                             | Read stored user facts, likes, and dislikes                                             |
| `personal_finance.add_credit_card`        | Register a credit card with limit, APR, and billing dates                               |
| `personal_finance.add_loan`               | Register a loan with balance, APR, and payment schedule                                 |
| `personal_finance.add_income`             | Record an income entry (one-time or recurring)                                          |
| `personal_finance.add_expense`            | Record an expense with category and date                                                |
| `personal_finance.get_report`             | Generate a monthly financial summary: burn rate and daily budget                        |
| `personal_finance.list_conflicts`         | List pending duplicate-entry conflicts awaiting resolution                              |
| `personal_finance.payment_to_credit_card` | Record a payment made toward a credit card balance                                      |
| `personal_finance.payment_to_loan`        | Record a payment made toward a loan balance                                             |
| `personal_finance.transferred_to_savings` | Record a transfer to savings                                                            |

## Frontend features

- **Multi-session sidebar** — create, switch, and delete chat sessions; history reloads from Redis on selection.
- **Tool call bubbles** — each tool invocation shows its name; click the bubble to expand arguments and result.
- **Reasoning bubbles** — extended thinking tokens are surfaced in a collapsible bubble; a global checkbox in the chat bar keeps all reasoning bubbles expanded or collapsed.
- **Cache badge** — assistant messages show whether the response came from the LLM or the semantic cache (Ollama only).
- **Context usage badge** — shows estimated token usage vs. the context window limit, updated after each turn.
- **File upload** — attach CSV or image files via presigned S3 URL; the agent reads CSVs with `csv_s3` and images with `image_read`.
- **Summarization progress** — tool bubbles display a live chunk counter (`chunk N / total`) while the summarizer is running, with a cancel button to abort the in-flight request.
- **Message history** — up/down arrow (without Shift) cycles through sent messages.

## Known Issues

For a comprehensive list of issues, bugs, and limitations, see [ISSUES.md](./ISSUES.md).
