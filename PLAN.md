# Plan: Micro Kernel Architecture for Tools

## 1. Motivation

The current tool architecture tightly couples every tool to LangChain's `StructuredTool` format. Each tool:

- Wraps itself through `make_session_tool()` → `record_tool_result()`
- Receives a `session_id_provider` callable as its only dependency
- Has no lifecycle hooks (init, shutdown, health)
- Cannot discover or invoke other tools
- Has no access to kernel-level services (cache, memory, storage) except by importing globals

The micro kernel architecture decouples tools from LangChain entirely. Tools become pure plugins that implement a simple Python interface. The kernel handles all framework integration, cross-cutting concerns, service discovery, and inter-tool communication.

---

## 2. Target Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        LangGraph Agent                           │
│  (still uses StructuredTool at the boundary)                     │
└──────────────────────────┬───────────────────────────────────────┘
                           │  tool calls via StructuredTool (compat layer)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                         TOOL KERNEL                              │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────────────┐   │
│  │ Middleware  │  │ Middleware  │  │   Middleware Chain       │   │
│  │ Chain (pre) │─▶│ Chain (post)│─▶│ (logging, metrics,      │   │
│  │            │  │            │  │  rate-limit, retry, ...)  │   │
│  └────────────┘  └────────────┘  └──────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Kernel Services                          │   │
│  │  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │ Context   │ │ Storage   │ │ EventBus │ │ Result   │  │   │
│  │  │ Service   │ │ Service   │ │ (pub/sub)│ │ Processor│  │   │
│  │  └───────────┘ └───────────┘ └──────────┘ └──────────┘  │   │
│  │  ┌───────────┐ ┌───────────┐ ┌──────────┐               │   │
│  │  │ Memory    │ │ Cache     │ │ Metrics  │               │   │
│  │  │ Service   │ │ Service   │ │ Service  │               │   │
│  │  └───────────┘ └───────────┘ └──────────┘               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │               Plugin Registry                             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ http_fetch│ │ csv_s3   │ │ sql_query│ │ weather  │ ... │   │
│  │  │ plugin   │ │ plugin   │ │ plugin   │ │ plugin   │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                           │
                           ▼
               ┌─────────────────────┐
               │   Storage Layer     │
               │  (Redis / InMemory) │
               └─────────────────────┘
```

---

## 3. Plugin Interface (`ToolPlugin`)

Every tool implements this abstract base class:

```python
class ToolPlugin(ABC):
    """Interface every tool plugin must implement."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def args_schema(self) -> type[BaseModel]: ...

    @abstractmethod
    async def execute(self, context: ToolContext, **kwargs: Any) -> str: ...

    # --- Lifecycle hooks (optional) ---

    async def on_init(self, kernel: "ToolKernel") -> None:
        """Called once when the kernel loads this plugin. Use for setup."""

    async def on_shutdown(self) -> None:
        """Called when the kernel shuts down. Use for cleanup."""

    async def on_health(self) -> dict[str, Any]:
        """Optional health-check endpoint data."""
        return {}
```

### What changes for existing tool authors:

| Before | After |
|---|---|
| `async def _run(arg: str)` | `async def execute(self, context: ToolContext, **kwargs)` |
| `factory(session_id_provider)` | `class XPlugin(ToolPlugin)` with static metadata |
| Imports `make_session_tool` from `tools/base.py` | No LangChain imports in tool code |
| Calls `record_tool_result` implicitly via wrapper | Result goes through `context.result.process()` |
| Accesses Redis directly via `boto3` / `httpx` | Uses `context.services.storage` or `context.services.memory` |
| No knowledge of other tools | Can call `context.call_tool("name", **args)` |

---

## 4. ToolContext

The context object passed to every `execute()` call:

```python
@dataclass
class ToolContext:
    session_id: str
    user_id: str | None          # from auth (future)
    request_id: str              # unique per LLM → tool invocation
    services: KernelServices     # typed service accessor
    kernel: "ToolKernel"         # back-reference for call_tool()

    async def call_tool(self, name: str, /, **kwargs: Any) -> str:
        """Invoke another tool through the kernel (kernel-mediated inter-tool comms)."""
        return await self.kernel.execute_tool(name, self, **kwargs)
```

Under the hood, `ToolContext` instance is stored in a `ContextVar` — the same pattern as the current `_current_session` but elevated to a full context object:

```python
_current_context: ContextVar[ToolContext] = ContextVar("tool_context")
```

---

## 5. Kernel Services

Services are available via `context.services.<service_name>`:

### 5.1 ResultProcessor

Handles the truncation/summarization policy (replaces `session/manager.py`):

```python
class ResultProcessor:
    async def process(
        self,
        tool_name: str,
        tool_args: dict,
        payload: str,
        *,
        inline_limit: int = 4000,
        summarize_limit: int = 8000,
    ) -> dict[str, Any]:
        """Returns the agent-facing metadata envelope (same shape as today)."""
```

Moves `record_tool_result` and `summarize` logic out of standalone functions and into this service. Fires `on_result` events on the event bus for observability.

### 5.2 StorageService

Provides a single, backend-agnostic persistence API:

```python
class StorageService:
    async def put_result(self, record: ToolResultRecord, payload: str) -> None: ...
    async def get_payload(self, handle: str) -> str | None: ...
    async def get_record(self, handle: str) -> ToolResultRecord | None: ...
    async def put_session(self, session_id: str, title: str) -> SessionRecord: ...
    async def list_sessions(self) -> list[SessionRecord]: ...
    async def delete_session(self, session_id: str) -> None: ...
```

Replaces direct usage of `get_store()`. Internally delegates to `RedisSessionStore` / `InMemoryStore`.

### 5.3 EventBus (for inter-tool communication)

```python
class EventBus:
    async def publish(self, event: str, payload: dict) -> None: ...
    async def subscribe(self, event: str, handler: Callable) -> None: ...
    async def request(self, target_tool: str, **kwargs) -> str: ...
```

`request()` is the mechanism for kernel-mediated tool calls. When tool A needs data from tool B:
1. Tool A calls `context.call_tool("tool_b", arg1=val1)`
2. Kernel validates the call, sets up middleware, invokes tool B
3. Result flows back through the same post-processing pipeline
4. Tool A receives the string result

### 5.4 MemoryService

Wraps the existing `MemoryStore` singleton with a clean API:

```python
class MemoryService:
    async def get_user_memory(self, user_id: str) -> dict: ...
    async def save_user_memory(self, user_id: str, data: dict) -> None: ...
```

### 5.5 CacheService

Wraps the semantic cache:

```python
class CacheService:
    async def check(self, prompt: str) -> str | None: ...
    async def store(self, prompt: str, response: str) -> None: ...
```

### 5.6 MetricsService

Collects execution data for every tool call:

```python
class MetricsService:
    async def record_call(self, tool_name: str, duration_ms: float, status: str, token_count: int) -> None: ...
    def get_collector(self) -> MetricsCollector: ...
```

---

## 6. Middleware System

The kernel supports a chain of middleware that wraps every tool execution:

```python
class ToolMiddleware(ABC):
    @abstractmethod
    async def before_execute(self, context: ToolContext, tool: ToolPlugin, kwargs: dict) -> None: ...

    @abstractmethod
    async def after_execute(self, context: ToolContext, tool: ToolPlugin, result: str, duration_ms: float) -> None: ...

    @abstractmethod
    async def on_error(self, context: ToolContext, tool: ToolPlugin, error: Exception) -> None: ...
```

Built-in middleware:

| Middleware | Purpose |
|---|---|
| `LoggingMiddleware` | Logs every tool call with duration and status |
| `MetricsMiddleware` | Records call count, duration, token usage per tool |
| `ErrorHandlingMiddleware` | Wraps exceptions into consistent error envelopes |
| `RateLimitMiddleware` | Per-tool rate limiting (configurable) |
| `RetryMiddleware` | Automatic retry with backoff for transient failures |
| `ValidationMiddleware` | Schema validation before execution |

---

## 7. ToolKernel (the core)

```python
class ToolKernel:
    def __init__(self):
        self._plugins: dict[str, ToolPlugin] = {}
        self._middleware: list[ToolMiddleware] = []
        self.services: KernelServices = KernelServices(...)

    def register(self, plugin: ToolPlugin) -> None:
        """Register a tool plugin."""

    def use(self, middleware: ToolMiddleware) -> None:
        """Add middleware to the chain."""

    async def init(self) -> None:
        """Initialize all plugins (calls on_init for each)."""

    async def shutdown(self) -> None:
        """Shut down all plugins gracefully."""

    async def execute_tool(
        self,
        name: str,
        context: ToolContext,
        **kwargs: Any,
    ) -> str:
        """Execute a tool by name through the full middleware chain."""

    def build_langchain_tools(self) -> list[StructuredTool]:
        """Wrap every registered plugin into LangChain StructuredTool format.
        
        This is the ONLY place LangChain is imported in the tools layer.
        """
```

### LangChain compatibility layer

`build_langchain_tools()` creates a `StructuredTool` wrapper per plugin:

```python
def build_langchain_tools(self) -> list[StructuredTool]:
    tools = []
    for plugin in self._plugins.values():
        tool = StructuredTool.from_function(
            name=plugin.name,
            description=plugin.description,
            args_schema=plugin.args_schema,
            coroutine=self._make_langchain_coro(plugin),
        )
        tools.append(tool)
    return tools

def _make_langchain_coro(self, plugin: ToolPlugin):
    async def _coro(**kwargs):
        ctx = _current_context.get()
        return await self.execute_tool(plugin.name, ctx, **kwargs)
    return _coro
```

---

## 8. Lifecycle

### Startup

```
┌─────────────────────────────────────────────────────────────┐
│ 1. ToolKernel() created                                     │
│ 2. All ToolPlugin instances instantiated                    │
│ 3. Each instance registered with kernel.register(plugin)    │
│ 4. Kernel services initialized (Storage, EventBus, ...)    │
│ 5. Middleware chain assembled                               │
│ 6. Each plugin.on_init(kernel) called                       │
│ 7. kernel.build_langchain_tools() → list[StructuredTool]   │
│ 8. Passed to LangGraph graph                                │
└─────────────────────────────────────────────────────────────┘
```

### Per-Request (tool execution)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. LangGraph ToolNode calls StructuredTool._coro(**kwargs)  │
│ 2. Kernel creates ToolContext (from ContextVar)             │
│ 3. Middleware.before_execute() chain runs                   │
│ 4. plugin.execute(context, **kwargs) runs                   │
│ 5. Result flows through context.services.result.process()   │
│ 6. Middleware.after_execute() chain runs                    │
│ 7. Metadata envelope returned to LLM                        │
└─────────────────────────────────────────────────────────────┘
```

### Shutdown

```
┌─────────────────────────────────────────────────────────────┐
│ 1. kernel.shutdown() called                                 │
│ 2. Each plugin.on_shutdown() called (reverse order)         │
│ 3. Kernel services closed                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. Migration Guide: Existing Tool → Plugin

### Example: `http_fetch.py` (before)

```python
class HttpFetchArgs(BaseModel):
    url: str = Field(...)
    method: str = Field("GET")
    max_bytes: int = Field(2_000_000)

async def _run(url: str, method: str = "GET", max_bytes: int = 2_000_000) -> str:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.request(method, url)
    ...

def factory(session_id_provider):
    return make_session_tool(
        name="http_fetch", description="...",
        args_schema=HttpFetchArgs, runner=_run,
        session_id_provider=session_id_provider,
    )
```

### Example: `http_fetch.py` (after)

```python
class HttpFetchArgs(BaseModel):
    url: str = Field(...)
    method: str = Field("GET")
    max_bytes: int = Field(2_000_000)

class HttpFetchPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "http_fetch"

    @property
    def description(self) -> str:
        return "Fetch a URL over HTTP(S) and return the body. ..."

    @property
    def args_schema(self) -> type[BaseModel]:
        return HttpFetchArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        url = kwargs["url"]
        method = kwargs.get("method", "GET")
        max_bytes = kwargs.get("max_bytes", 2_000_000)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.request(method, url)
        text = resp.text
        if len(text.encode("utf-8")) > max_bytes:
            text = text[:max_bytes] + "\n... [truncated]"
        return f"HTTP {resp.status_code} {url}\n\n{text}"
```

No `make_session_tool` call. No `factory` function. No LangChain import. The kernel handles all the wrapping.

---

## 10. File Structure (After)

```
backend/src/app/tools/
├── __init__.py              # Exports ToolKernel, build_tools_from_kernel
├── kernel.py                # ToolKernel class
├── plugin.py                # ToolPlugin ABC, ToolContext, KernelServices
├── middleware.py             # ToolMiddleware ABC + built-in middleware
├── services/
│   ├── __init__.py           # KernelServices container
│   ├── result.py            # ResultProcessor (moved from session/manager.py)
│   ├── storage.py           # StorageService (wraps SessionStore)
│   ├── event_bus.py         # EventBus for inter-tool communication
│   ├── memory.py            # MemoryService (wraps MemoryStore)
│   ├── cache.py             # CacheService (wraps SemanticCache)
│   └── metrics.py           # MetricsService
├── plugins/
│   ├── __init__.py           # ALL_PLUGINS list
│   ├── http_fetch.py        # → HttpFetchPlugin
│   ├── csv_s3.py            # → CsvS3Plugin
│   ├── image_s3.py          # → ImageS3Plugin
│   ├── sql_query.py         # → SqlQueryPlugin
│   ├── sql_ddl.py           # → SqlDdlPlugin
│   ├── sql_dml.py           # → SqlDmlPlugin
│   ├── weather_api.py       # → WeatherPlugin
│   ├── recall.py            # → RecallPlugin
│   ├── save_memory.py       # → SaveMemoryPlugin
│   └── read_memory.py       # → ReadMemoryPlugin
│
# Removed / no longer needed:
#   base.py                  # replaced by kernel.py + plugin.py
#   registry.py              # replaced by plugins/__init__.py
```

Key: `session/manager.py` moves into `tools/services/result.py`. The `record_tool_result` function becomes `ResultProcessor.process()`. The store layer stays in `session/store.py` but is wrapped by `StorageService`.

---

## 11. Integration with LangGraph (minimal changes)

The LangGraph graph in `agent/graph.py` currently does:

```python
_TOOLS = build_tools(_session_id)
_LLM = build_chat_llm().bind_tools(_TOOLS)
```

After the migration:

```python
_kernel = ToolKernel()
# ... plugins registered, middleware added ...
await _kernel.init()
_TOOLS = _kernel.build_langchain_tools()
_LLM = build_chat_llm().bind_tools(_TOOLS)
```

The `_session_id` context var is still set by `_bind_session()`. The kernel's `execute_tool()` reads it through the `_current_context` ContextVar.

The `ToolNode` in the LangGraph graph receives `_TOOLS` (which are still `StructuredTool` instances), so the graph code changes minimally — or not at all if we build the kernel at module level the same way `build_tools` is called today.

---

## 12. Changes to `session/` and `agent/` Modules

### `session/manager.py`

- `record_tool_result()` → moved into `tools/services/result.py` as `ResultProcessor.process()`
- `recall_payload()` → moved into `tools/services/result.py` or kept as thin wrapper in `StorageService`
- `_short_preview()` → private helper in `ResultProcessor`
- Replaced by a public `ResultProcessor` class that uses the same `_tokens()` logic, the same `summarize()` call, and the same `ToolResultRecord` model

### `session/store.py`

- Stays as-is (it's a storage implementation, not a tool concern)
- Gets wrapped by `StorageService` in `tools/services/storage.py`

### `agent/graph.py`

- Import `_kernel` instead of `build_tools`
- Call `_kernel.build_langchain_tools()` instead of `build_tools(_session_id)`
- Everything else remains unchanged

### `api/routes.py`

- No changes needed

---

## 13. Testing Strategy

### Unit tests per plugin

```python
# tests/plugins/test_http_fetch.py
async def test_http_fetch_success():
    plugin = HttpFetchPlugin()
    ctx = fake_context()
    result = await plugin.execute(ctx, url="http://example.com")
    assert "HTTP 200" in result
```

No LangChain, no session manager, no Redis. Pure business logic test.

### Kernel integration tests

```python
# tests/test_kernel.py
async def test_kernel_wraps_tool_into_structured_tool():
    kernel = ToolKernel()
    kernel.register(MyTestPlugin())
    await kernel.init()
    langchain_tools = kernel.build_langchain_tools()
    assert len(langchain_tools) == 1
    assert isinstance(langchain_tools[0], StructuredTool)

async def test_middleware_chain():
    kernel = ToolKernel()
    kernel.use(TestMiddleware())
    kernel.register(MyTestPlugin())
    await kernel.init()
    result = await kernel.execute_tool("test", fake_context(), arg="val")
    assert middleware_was_called
```

### Inter-tool communication tests

```python
async def test_tool_a_calls_tool_b():
    kernel = ToolKernel()
    kernel.register(ToolAPlugin())
    kernel.register(ToolBPlugin())
    await kernel.init()
    ctx = ToolContext(session_id="test", ..., kernel=kernel)
    result = await kernel.execute_tool("tool_a", ctx)
    assert "from_tool_b" in result
```

### Migration tests

Existing `test_session_manager.py` tests continue to work because `ResultProcessor.process()` implements the same logic as `record_tool_result()`.

---

## 14. Migration Steps (in order)

### Phase 1: Core kernel infrastructure

1. Create `tools/plugin.py` — `ToolPlugin` ABC, `ToolContext`, `KernelServices`, `_current_context` ContextVar
2. Create `tools/kernel.py` — `ToolKernel` class with register, use, init, shutdown, execute_tool, build_langchain_tools
3. Create `tools/middleware.py` — `ToolMiddleware` ABC
4. Create `tools/services/__init__.py` — `KernelServices` container dataclass
5. Create `tools/services/result.py` — `ResultProcessor` (move logic from `session/manager.py`)
6. Create `tools/services/storage.py` — `StorageService` wrapper around `get_store()`
7. Create `tools/services/event_bus.py` — `EventBus` for inter-tool comms
8. Create `tools/services/memory.py` — wraps `MemoryStore`
9. Create `tools/services/cache.py` — wraps `SemanticCache`
10. Create `tools/services/metrics.py` — `MetricsService`

### Phase 2: Migrate tools → plugins

11. Create `tools/plugins/__init__.py` — consolidated `ALL_PLUGINS` list
12. Migrate `http_fetch.py` → `tools/plugins/http_fetch.py` (as `HttpFetchPlugin`)
13. Migrate `csv_s3.py` → `tools/plugins/csv_s3.py`
14. Migrate `image_s3.py` → `tools/plugins/image_s3.py`
15. Migrate `sql_query.py` → `tools/plugins/sql_query.py`
16. Migrate `sql_ddl.py` → `tools/plugins/sql_ddl.py`
17. Migrate `sql_dml.py` → `tools/plugins/sql_dml.py`
18. Migrate `weather_api.py` → `tools/plugins/weather_api.py`
19. Migrate `recall.py` → `tools/plugins/recall.py`
20. Migrate `save_memory.py` → `tools/plugins/save_memory.py`
21. Migrate `read_memory.py` → `tools/plugins/read_memory.py`

Each migration: rename `factory` + `_run` into a `class XPlugin(ToolPlugin)`, remove `make_session_tool` import, remove `session_id_provider` parameter.

### Phase 3: Wire kernel into the app

22. Update `tools/__init__.py` — export `create_kernel()` factory function
23. Update `agent/graph.py` — use `create_kernel()` instead of `build_tools(_session_id)`
24. Remove `tools/base.py`, `tools/registry.py`
25. Remove `session/manager.py` (logic lives in `tools/services/result.py`)
26. Update imports in `tools/plugins/recall.py` to point to new `ResultProcessor` location

### Phase 4: Middleware and advanced features

27. Add `LoggingMiddleware`
28. Add `MetricsMiddleware`
29. Add `ErrorHandlingMiddleware`
30. Add inter-tool communication: wire `EventBus.request()` → `kernel.execute_tool()` with cycle detection

### Phase 5: Cleanup

31. Remove dead code: `tools/base.py`, `tools/registry.py`, old standalone tool files
32. Update `tests/` — add plugin-level unit tests, kernel integration tests
33. Verify `pytest` passes
34. Verify `npm run build` on frontend (no frontend changes expected)
35. Update `DESIGN.md` and `CLAUDE.md`

---

## 15. Inter-Tool Communication Design

The EventBus enables kernel-mediated tool-to-tool calls:

```python
# Plugin A needs data from Plugin B
class ReportPlugin(ToolPlugin):
    async def execute(self, context: ToolContext, **kwargs) -> str:
        # Fetch raw data via another tool
        weather_data = await context.call_tool("weather_lookup", latitude=51.5, longitude=-0.12)
        csv_data = await context.call_tool("csv_read", source="s3://bucket/data.csv")
        return f"Weather: {weather_data}\n\nCSV: {csv_data}"
```

The kernel ensures:

- **Cycle detection**: a `set[str]` of currently-executing tool names is tracked; if tool A calls tool B which calls tool A, the second call raises `ToolCycleError`
- **Reentrancy**: each nested call gets its own middleware chain invocation
- **Context propagation**: the same `ToolContext` is passed through
- **Result processing**: Results of nested calls still go through the `ResultProcessor`

---

## 16. Backward Compatibility

- The LangGraph graph continues to receive `list[StructuredTool]` — zero changes to LangGraph integration
- The `ToolNode` in `graph.py` does not change
- The SSE event format does not change
- The API routes (`routes.py`) do not change
- The `ToolResultRecord` model does not change
- The `agent_view()` envelope format does not change

The only visible change is internal: tools are now plugins managed by a kernel.

---

## 17. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Big bang rewrite breaks everything at once | Phase the migration; write integration tests in Phase 1 before touching any tool |
| ContextVar pattern gets complex with nested calls | Document the reentrance model; add explicit tests for nested `call_tool` |
| Performance overhead from middleware chain | Keep middleware lightweight; use `__slots__` on context objects; benchmark before/after |
| Plugin interface too rigid for diverse tools | Make lifecycle hooks optional (`on_init` has a no-op default); keep `execute` signature flexible |
| Circular imports between kernel and services | Single `KernelServices` container in a dedicated module; services receive back-ref to kernel at init time |
