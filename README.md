# Multi-Tool Chat Application

Full-stack chat application where a LangGraph agent invokes multiple tools, with a Session Manager that persists tool results and a summarization sub-agent for oversized output.

## Architecture

```
┌────────────┐  SSE  ┌─────────────────────────────┐
│ React/Vite │──────▶│ FastAPI + LangGraph          │
└────────────┘       │  ┌──────────────┐            │
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
                     │  │  sql_query   │           │ │
                     │  │  sql_ddl     │           │ │
                     │  │  sql_dml     │           │ │
                     │  │  weather     │           │ │
                     │  │  recall      │           │ │
                     │  │  save_memory │           │ │
                     │  │  read_memory │           │ │
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
```

Key design choices:

- **Session Manager owns the truncation policy.** Every tool routes its output through `record_tool_result`. Small results are returned inline; oversized results are summarized and persisted, with only `{handle, summary, size, ...}` returned to the agent.
- **`recall(handle)` is an explicit tool.** The agent decides when to bring full content back. This satisfies the requirement: "use metadata from stored results to decide whether a result should be brought back into the context window."
- **Summarizer is map-reduce.** Truly large payloads are chunked, summarized per chunk, then reduced.
- **Semantic cache.** Redis-backed `SemanticCache` with vector embeddings de-duplicates repeated queries across sessions (shared cache, distance threshold 0.09, 5-minute TTL), returning cached responses without hitting the LLM. Requires Ollama (`LLM_PROVIDER=ollama`) — silently disabled when using Anthropic because Anthropic has no first-party embedding API in LangChain.
- **Redis is the single backing store.** Session metadata, tool-result payloads, LangGraph checkpoints, the semantic cache, and the long-term memory store all live in Redis — no DynamoDB required.
- **Long-term memory tools.** `save_memory` and `read_memory` persist user facts, likes, and dislikes across sessions via Redis.

## Layout

```
backend/        Python (FastAPI + LangGraph), Pants targets
  src/app/
    api/        HTTP routes (SSE chat stream, session CRUD, upload_url)
    agent/      LangGraph graph, summarizer, semantic cache, vectorizer
    session/    Session Manager (RedisSessionStore + models)
    tools/      http_fetch, csv_s3, sql_query, sql_ddl, sql_dml,
                weather, recall, save_memory, read_memory
    upload/     Presigned S3 URL generation
  tests/
  Dockerfile
frontend/       React + Vite + TS chat UI
  src/
    components/ NavBar, Header, ChatBox, FileUpload, FileItem,
                BubbleUser, BubbleAssistant, BubbleTool, BubbleReasoning,
                ChatLoadingIndicator, ConfirmDialog
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

# 2. Build & push the API image to ECR
ECR=$(terraform output -raw ecr_repo)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR
docker build -t $ECR:latest ../../../backend
docker push $ECR:latest
aws ecs update-service --cluster mtc-dev-cluster --service mtc-dev-api --force-new-deployment

# 3. Build & upload frontend
cd ../../../frontend
npm run build
SITE=$(cd ../infra/envs/dev && terraform output -raw frontend_url)
aws s3 sync dist/ s3://mtc-dev-frontend/
```

(With Pants: `pants package backend:api-image` builds the image; tag and push it to the ECR URL above.)

## Required env (backend)

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `anthropic` (default) or `ollama` |
| `ANTHROPIC_API_KEY` | LLM access when `LLM_PROVIDER=anthropic` |
| `MODEL_NAME` | Override main LLM (default: `claude-sonnet-4-6`) |
| `SUMMARIZER_MODEL` | Override summarizer (default: `claude-haiku-4-5-20251001`) |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Ollama chat model (default: `qwen2.5:7b`) |
| `OLLAMA_SUMMARIZER_MODEL` | Ollama summarizer model |
| `OLLAMA_EMBEDDING_MODEL` | Ollama embedding model for semantic cache (default: `embeddinggemma`) |
| `REDIS_URL` | Redis connection string (default: `redis://localhost:6379`) |
| `EXTERNAL_S3_ENDPOINT_URL` | S3 endpoint reachable from the browser (presigned URLs) |
| `INTERNAL_S3_ENDPOINT_URL` | S3 endpoint reachable from the backend container |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | S3 credentials |
| `BUCKET_NAME` | S3 bucket for file uploads |
| `USE_AWS_STORE` | `1` to use DynamoDB+S3 for session/tool-result storage (unset = Redis) |

## Tool reference

| Tool | Description |
| --- | --- |
| `http_fetch` | Fetch a URL and return the response body |
| `csv_s3` | Read a CSV file from S3 |
| `sql_query` | Run a SELECT query against the local SQLite DB |
| `sql_ddl` | Run CREATE / DROP / ALTER TABLE statements |
| `sql_dml` | Run INSERT / UPDATE / DELETE statements |
| `weather` | Get current weather for a location |
| `recall` | Retrieve a full tool-result payload by handle |
| `save_memory` | Persist user facts, likes, and dislikes across sessions |
| `read_memory` | Read stored user facts, likes, and dislikes |

## Frontend features

- **Multi-session sidebar** — create, switch, and delete chat sessions; history reloads from Redis on selection.
- **Tool call bubbles** — each tool invocation shows its name; click the bubble to expand arguments and result.
- **Reasoning bubbles** — extended thinking tokens are surfaced in a collapsible bubble; a global checkbox in the chat bar keeps all reasoning bubbles expanded or collapsed.
- **Cache badge** — assistant messages show whether the response came from the LLM or the semantic cache (Ollama only).
- **File upload** — attach CSV files via presigned S3 URL; the agent can then read them with `csv_s3`.
- **Message history** — up/down arrow cycles through sent messages.

## Known Issues

For a comprehensive list of issues, bugs, and limitations, see [ISSUES.md](./ISSUES.md).
