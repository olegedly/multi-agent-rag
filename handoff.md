# Handoff: ADK → LangChain — Frontend Wiring

## Transition Story

The project was originally built on **Google ADK** (`ag_ui_adk` → `ADKAgent` → `AdkLlmAdapter` → custom `LLMClient` protocol). The ADK state pipeline had a critical bug: `corpusId` sent by the frontend in the POST body never reached `tool_context.state` inside the RAG tool functions. Every single RAG query returned `"No active corpus"`.

We migrated to **LangChain** (`create_agent` / `@tool` decorators) in a single TDD session. The custom `LLMClient` protocol, provider implementations (OpenAI/Anthropic), HTTP transport layer, and the ADK adapter bridge are all gone — replaced by `langchain-openai` `ChatOpenAI` / `ChatAnthropic`.

## What Was Achieved (Backend)

| Layer | Before (ADK) | After (LangChain) |
|---|---|---|
| Agent | `Agent(model=AdkLlmAdapter(...), tools=[FunctionTool(...)])` | `create_agent(model=ChatOpenAI(...), tools=[...])` |
| Tool factory | `make_rag_tools()` → ADK functions reading `tool_context.state["corpusId"]` | `create_rag_tools(corpus_id=X)` → LangChain `@tool` with `corpus_id` in closure |
| Endpoint | `add_adk_fastapi_endpoint(app, ADKAgent(...), path="/api/chat")` | Raw `@app.post("/api/chat/{slug}")` with SSE `StreamingResponse` |
| Streaming | ADK's internal SSE → `ag_ui_adk` marshalling | TanStack AI SSE format via `async for event in run_pipeline(...)` |
| Routing | Generic `/api/chat` — corpusId in `body.state` | Route-based `POST /api/chat/{slug}` — slug resolves via `CorporaConfig.get(slug)` |

Key files created:
- `backend/agents/langchain_tools.py` — `create_rag_tools(corpus_id, ...)` factory
- `backend/agents/pipeline.py` — LangChain `create_agent` pipeline, yields TanStack SSE dicts
- `backend/main.py` — rewritten: no ADK imports, slug-based SSE endpoint

Key files removed:
- `backend/agents/tools.py` — ADK `tool_context.state` pattern
- `backend/llm/adk_adapter.py` — ADK `BaseLlm` bridge
- `tests/agents/test_tools.py`, `tests/test_main.py`, `tests/llm/test_adk_adapter.py`

Current state: **208 tests pass**, all green. The old `backend/llm/` protocol files still exist (`protocol.py`, `openai.py`, `anthropic.py`, `transport.py`, `factory.py`) because `backend/embeddings/openai.py` shares `LLMError` and `HttpTransport` with them. They are stable, tested infrastructure — keep unless the embeddings module gets refactored.

## What the Frontend Needs

**Minimal change:** the frontend currently hits `POST /api/chat` with `body.state.corpusId` in the payload. The backend now expects `POST /api/chat/{slug}` where the slug is from `corpora.yaml` (e.g. `"eu-ai-act"`). The `body` parameter is also deprecated in TanStack AI — the modern way is `forwardedProps`.

### The Change (one file: `frontend/src/conversations/useChatStore.ts`)

```typescript
// BEFORE (ADK)
const chat = useChat({
    connection: fetchServerSentEvents("/api/chat", {
        fetchClient: resilientFetch,
    }),
    body: {
        state: { corpusId: "315e41aa-8657-46c0-ac4b-ea4355babf0a" },
    },
});

// AFTER (LangChain) — hardcoded slug for now
const chat = useChat({
    connection: fetchServerSentEvents("/api/chat/eu-ai-act", {
        fetchClient: resilientFetch,
    }),
});
```

That's it. Remove the entire `body` property (it was the deprecated AG-UI pattern for injecting state, which the ADK was supposed to propagate to `tool_context.state` but never did). Remove `forwardedProps` too — not needed since the corpus routing is now URL-based.

The corpus slug `"eu-ai-act"` matches the entry in `backend/corpora.yaml`:
```yaml
corpora:
  - id: "315e41aa-8657-46c0-ac4b-ea4355babf0a"
    slug: "eu-ai-act"
    name: "EU AI Act"
    description: "European Union Artificial Intelligence Act..."
    chunker: "markdown-heading"
    documents: "corpora/eu-ai-act/**/*.md"
```

### Everything Else Stays

- `resilientFetch` — still works (handles non-ok responses)
- `store.ts` — conversation persistence, no changes
- `ChatView.tsx` — rendering, no changes
- `App.tsx` — layout/theme, no changes
- `Sidebar.tsx` — conversation list, no changes
- `title.ts` — title derivation, no changes

### Wiring Diagram

```
Frontend (SolidJS + @tanstack/ai-solid)
    │ POST /api/chat/eu-ai-act
    │ body: { messages: [...] }
    ▼
POST /api/chat/{slug} (FastAPI)
    │
    ├─ ChatGuard (budget + query validation)
    │
    └─ run_pipeline(messages, slug)
            │
            ├─ CorporaConfig.get(slug) → corpus UUID
            ├─ create_rag_tools(corpus_id=uuid) → [rag_search, rag_read_document]
            ├─ create_agent(model=ChatOpenAI(...), tools=[...])
            │       └─ agent.ainvoke({"messages": [...]})
            └─ yields TanStack SSE dicts → SSE stream → frontend
```

## Remaining Work (After Frontend Fix)

1. **Multi-agent pipeline** — currently single-agent Researcher. Critic and Synthesizer roles are planned but not implemented.
2. **Usage callback for budget** — the old ADK adapter had `usage_callback` that incremented the budget file. LangChain's `ChatOpenAI` has callbacks for this, but they haven't been wired yet.
3. **Corpus picker UI** — the frontend would eventually let users choose which corpus to query, deriving the slug dynamically. Right now it's hardcoded.
