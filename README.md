# Multi-Tool Chat Application

Full-stack chat application where a LangGraph agent invokes multiple tools, with a Session Manager that persists tool results and a summarization sub-agent for oversized output.

## Architecture

```
┌────────────┐  SSE  ┌───────────────────────────────┐
│ React/Vite │──────▶│ FastAPI + LangGraph           │
└────────────┘       │  ┌──────────────┐             │
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
                     │  │  weather_lookup          │ │
                     │  │  recall      │           │ │
                     │  │  save_memory │           │ │
                     │  │  read_memory │           │ │
                     │  │  personal_finance.*      │ │
                     │  │  rag_upload  │           │ │
                     │  │  rag_search  │           │ │
                     │  │  rag_queue_status        │ │
                     │  │  rag_list    │           │ │
                     │  │  rag_delete  │           │ │
                     │  │  doc_preview │           │ │
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
                           │ PostgreSQL │  (personal finance data,
                           │            │   RAG document chunks)
                           └────────────┘

                           ┌──────────────────────┐
                           │ MCP Weather Service  │  port 8002 — weather_lookup
                           └──────────────────────┘

                           ┌──────────────────────┐
                           │ MCP Documents Service│  port 8003 — rag_* + doc_preview
                           │ (chunking + pgvector)│
                           └──────────────────────┘

                           ┌──────────────────────┐
                           │ MCP Finance Service  │  port 8004 — personal_finance.*
                           │ (asyncpg + Postgres) │
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
- **Personal finance suite.** Nine tools under the `personal_finance.*` namespace track credit cards, loans, income, expenses, savings transfers, and monthly reports. The backend plugins are thin proxies — all DB logic lives in `mcp_personal_finance` (port 8004), a standalone FastMCP microservice that owns the Postgres schema and `asyncpg` pool.
- **MCP microservice tools.** Three standalone FastMCP services extend the tool set via the MCP protocol. `mcp_weather_service` (port 8002) handles geocoding and returns weather data; `mcp_documents` (port 8003) provides RAG capabilities — document chunking, pgvector-based embedding storage, Redis-backed ingestion queue, document listing/deletion, and document preview; `mcp_personal_finance` (port 8004) owns all personal-finance database access. All three are called by `ToolPlugin` subclasses using `fastmcp.client.Client` with `StreamableHttpTransport`, keeping the kernel and middleware unchanged.
- **RAG pipeline.** `rag_upload` queues an S3 document (txt, pdf, docx, pptx, xlsx, images) for async chunking and embedding by `mcp_documents`. A background worker embeds chunks via Ollama and stores them in PostgreSQL with pgvector. `rag_search` runs a cosine-similarity query over stored chunks and returns ranked results with temporary presigned S3 links. `rag_queue_status` shows the ingestion queue. `rag_list` lists all indexed documents with status, chunk count, and presigned download links. `rag_delete` removes a document from the index and deletes it from S3. `doc_preview` downloads and summarizes a document without indexing it.
- **LLM instance caching.** `agent/llm.py` caches `ChatAnthropic` / `ChatOllama` instances keyed by `(model, max_tokens, reasoning)`, avoiding re-construction on every request.

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
                    recall, save_memory, read_memory,
                    rag_upload, rag_search, rag_status,
                    rag_list, rag_delete, doc_preview)
                    personal_finance/ (9 thin MCP proxies:
                    add_credit_card, add_loan, add_income,
                    add_expense, get_report, list_conflicts,
                    payment_to_credit_card, payment_to_loan,
                    transferred_to_savings)
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
  mcp_weather_service/      FastMCP (port 8002) — get_weather tool
  mcp_documents/            FastMCP (port 8003) — RAG: chunking, pgvector storage,
                            Redis ingestion queue, async worker; exposes rag_upload,
                            rag_search, rag_queue_status, rag_list, rag_delete, doc_preview
  mcp_personal_finance/     FastMCP (port 8004) — personal finance DB logic; exposes
                            add_credit_card, add_loan, add_income, add_expense,
                            payment_to_credit_card, payment_to_loan, get_report,
                            list_conflicts, transferred_to_savings
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
ECR=$(terraform output -raw ecr_api)
ECR_WEATHER=$(terraform output -raw ecr_weather_service)
ECR_DOCS=$(terraform output -raw ecr_mcp_documents)
ECR_FINANCE=$(terraform output -raw ecr_mcp_personal_finance)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR
docker build -t $ECR:latest             ../../../backend
docker build -t $ECR_WEATHER:latest     ../../../services/mcp_weather_service
docker build -t $ECR_DOCS:latest        ../../../services/mcp_documents
docker build -t $ECR_FINANCE:latest     ../../../services/mcp_personal_finance
docker push $ECR:latest
docker push $ECR_WEATHER:latest
docker push $ECR_DOCS:latest
docker push $ECR_FINANCE:latest
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
| `POSTGRES_PASSWORD`                          | PostgreSQL password (used by Docker Compose, default: `finance_password`)                                                                |
| `EXTERNAL_S3_ENDPOINT_URL`                   | S3 endpoint reachable from the browser (presigned URLs)                                                                                  |
| `INTERNAL_S3_ENDPOINT_URL`                   | S3 endpoint reachable from the backend container                                                                                         |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | S3 credentials                                                                                                                           |
| `BUCKET_NAME`                                | S3 bucket for file uploads                                                                                                               |
| `USE_AWS_STORE`                              | `1` to use DynamoDB+S3 for session/tool-result storage (unset = Redis)                                                                   |
| `WEATHER_SERVICE_URL`                        | URL for the MCP weather microservice (default: `http://localhost:8002`)                                                                  |
| `RAG_SERVICE_URL`                            | URL for the MCP documents / RAG microservice (default: `http://localhost:8003`)                                                          |
| `FINANCE_SERVICE_URL`                        | URL for the MCP personal-finance microservice (default: `http://localhost:8004`)                                                         |

## Tool reference

| Tool                                      | Description                                                                                          |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `http_fetch`                              | Fetch a URL and return the response body                                                             |
| `csv_s3`                                  | Read a CSV file from S3; supports `filter_column`/`filter_value` for full-dataset scans              |
| `image_read`                              | Read an image from S3 and analyze it with the vision LLM; OCR supported                              |
| `sql_query`                               | Run a SELECT query against the local SQLite DB                                                       |
| `sql_ddl`                                 | Run CREATE / DROP / ALTER TABLE statements                                                           |
| `sql_dml`                                 | Run INSERT / UPDATE / DELETE statements                                                              |
| `weather_lookup`                          | Get current weather + hourly temperature forecast for a lat/lon via the FastMCP weather microservice |
| `recall`                                  | Retrieve a full tool-result payload by handle                                                        |
| `save_memory`                             | Persist user facts, likes, and dislikes across sessions                                              |
| `read_memory`                             | Read stored user facts, likes, and dislikes                                                          |
| `personal_finance.add_credit_card`        | Register a credit card with limit, APR, and billing dates                                            |
| `personal_finance.add_loan`               | Register a loan with balance, APR, and payment schedule                                              |
| `personal_finance.add_income`             | Record an income entry (one-time or recurring)                                                       |
| `personal_finance.add_expense`            | Record an expense with category and date                                                             |
| `personal_finance.get_report`             | Generate a monthly financial summary: burn rate and daily budget                                     |
| `personal_finance.list_conflicts`         | List pending duplicate-entry conflicts awaiting resolution                                           |
| `personal_finance.payment_to_credit_card` | Record a payment made toward a credit card balance                                                   |
| `personal_finance.payment_to_loan`        | Record a payment made toward a loan balance                                                          |
| `personal_finance.transferred_to_savings` | Record a transfer to savings                                                                         |
| `rag_upload`                              | Queue an S3 document (txt, pdf, docx, pptx, xlsx, images) for chunking and RAG indexing              |
| `rag_search`                              | Semantic search over RAG-indexed documents; returns ranked chunks with presigned S3 links            |
| `rag_queue_status`                        | Show the ordered list of documents pending or being processed by the RAG pipeline                    |
| `rag_list`                                | List all indexed documents with status, chunk count, dates, and presigned S3 download links; optionally filter by filename |
| `rag_delete`                              | Delete a document from the RAG index and remove it from S3 by its original `s3://` URL              |
| `doc_preview`                             | Preview a document or image from S3 without indexing it; returns a raw text snippet and an LLM-generated summary |

## Frontend features

- **Multi-session sidebar** — create, switch, and delete chat sessions; history reloads from Redis on selection.
- **Tool call bubbles** — each tool invocation shows its name; click the bubble to expand arguments and result.
- **Reasoning bubbles** — extended thinking tokens are surfaced in a collapsible bubble; a global checkbox in the chat bar keeps all reasoning bubbles expanded or collapsed.
- **Cache badge** — assistant messages show whether the response came from the LLM or the semantic cache (Ollama only).
- **Context usage badge** — shows estimated token usage vs. the context window limit, updated after each turn.
- **File upload** — attach CSV, image, or PDF files via presigned S3 URL; the agent reads CSVs with `csv_s3`, images with `image_read`, and can queue PDFs and other documents for RAG indexing with `rag_upload`.
- **External link rendering** — URLs in assistant messages open in a new tab via `rehype-external-links`.
- **Summarization progress** — tool bubbles display a live chunk counter (`chunk N / total`) while the summarizer is running, with a cancel button to abort the in-flight request.
- **Clear cache button** — a button fixed at the bottom of the sidebar calls `DELETE /cache` to flush the semantic cache (no-op when the cache is disabled).
- **Message history** — up/down arrow (without Shift) cycles through sent messages.

## Known Issues

For a comprehensive list of issues, bugs, and limitations, see [ISSUES.md](./ISSUES.md).
