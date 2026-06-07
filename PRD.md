# PRD: Multi-Agent RAG Research System (Portfolio Demo)

## Problem Statement

Organizations across the public and private sectors need intelligent research systems that can answer questions grounded in authoritative, curated knowledge — not sprawling web searches or unverified AI hallucinations. From compliance officers querying regulatory libraries to policy researchers navigating institutional archives, the demand for **grounded, cited, real-time research assistance** over well-defined knowledge bases is growing fast.

Building such a system requires mastery of the modern AI engineering stack:

1. Production FastAPI backends with Pydantic
2. RAG with PostgreSQL + pgvector
3. MCP servers as tool interfaces
4. Multi-agent orchestration with Google ADK
5. Real-time streaming agent output to a web UI
6. Containerized, deployable full-stack applications
7. Route-based, corpus-scoped retrieval across multiple curated knowledge bases

This project demonstrates all of the above in a single, deployable system: a multi-agent research assistant that serves grounded, cited answers from multiple curated public knowledge bases — each a first-class destination with its own route, its own corpus, and its own conversations.

## Solution

An interactive multi-agent research system where:

- A landing page introduces the system and lists the available curated knowledge bases
- Selecting a knowledge base navigates to a dedicated route for that corpus
- The user submits a research question within the context of that corpus
- Three specialist AI agents (Researcher, Critic, Synthesizer) collaborate via ADK to answer it
- Agents search only the active corpus in a pgvector knowledge base — retrieval is scoped by `corpus_id`
- The entire reasoning process streams to the dashboard in real-time — tool calls, intermediate findings, final synthesis
- The system is config-driven: LLM provider, model, and API endpoint are environment variables
- The frontend is a Vite + SolidJS SPA served as static files, connecting to the backend via `@tanstack/ai-solid`'s `useChat` hook over the AG-UI protocol
- The system is Dockerized for deployment, with a native `fastapi dev` workflow for local development

The architecture is intentionally corpus-scoped: each conversation is bound to one corpus from start to finish, every retrieval query carries the active corpus identifier, and adding a new knowledge base is primarily an ingestion and configuration task.

## User Stories

1. As a visitor, I want to land on a main page that introduces the system and shows the available knowledge bases, so that I can choose where to start my research.
2. As a visitor, I want to click on a knowledge base card to navigate to its dedicated route, so that I enter a research session scoped to that corpus.
3. As a visitor, I want to type a natural-language research question and have the system retrieve context from the active knowledge base only, so that answers are grounded in the right source.
4. As a visitor, I want to see each agent's reasoning and tool calls streamed in real-time, so that I understand the multi-agent collaboration process.
5. As a visitor, I want the final answer to include citations from the active knowledge base, so that I trust the output is grounded and not hallucinated.
6. As a visitor, I want to know which corpus the current conversation belongs to, so that I don't confuse answers across knowledge bases.
7. As a visitor, I want to start a new conversation within the same corpus without leaving the route, so that I can explore multiple questions on the same topic.
8. As a visitor, I want to return to the landing page to pick a different knowledge base, so that I can explore multiple corpora in separate sessions.
9. As a visitor, I want each conversation to show a title so I can identify it, and I want a sidebar listing my current conversations in this corpus for easy switching.
10. As a visitor, if I navigate to a stale or mistyped corpus slug, I want to stay on the route and see a friendly explanation with a button to the landing page, so that I understand what happened and can easily get back on track.
11. As a potential client, I want to see the system deployed at a live URL, so that I can evaluate it without running any code.
12. As a potential client, I want to see clean, production-quality code in a public repository, so that I can evaluate engineering practices.
13. As the developer, I want the LLM client to be abstracted behind a single interface that supports both OpenAI-format and Anthropic-format endpoints, so that I can explain to future clients that adapting to their preferred provider is a configuration change (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`), not a rewrite.
14. As the developer, I want the RAG pipeline to use pgvector with `corpus_id` scoping for semantic search, so that I can demonstrate vector database skills with multi-corpus isolation.
15. As the developer, I want the MCP server to accept a `corpus_id` parameter so tools operate within the correct scope, and to be independently runnable and testable.
16. As the developer, I want the system to run in Docker Compose with a single command, so that deployment is reproducible.
17. As the developer, I want ADK tracing instrumented on all agent calls, so that I can debug and demonstrate observability awareness.
18. As the developer, I want the frontend to be a vanilla SPA (no Next.js, no Vercel) served as static files, so that I retain full deployment flexibility.

## Implementation Decisions

### Architecture Overview

```
Landing Page
  │
  ├── /corpora/us-tax-code ─── Corpus-specific route (by slug)
  ├── /corpora/eu-ai-act  ─── Corpus-specific route (by slug)
  └── /corpora/uk-civil-procedure ─── Corpus-specific route (by slug)
        │
SolidJS SPA ──AG-UI/SSE──▶ FastAPI ──▶ Google ADK Orchestrator
  (@tanstack/ai-solid,     (create_app()    ├── Researcher (corpus-scoped)
   fetchServerSentEvents)   factory)        ├── Critic (corpus-scoped)
                                              └── Synthesizer (corpus-scoped)
                              │
                              ├── MCP Server (search_knowledge, fetch_document)
                              │         └── pgvector RAG (corpus-filtered)
                              │               └── PostgreSQL ── chunks with corpus_id
                              │
                              └── backend/llm/ layer
                                    ├── AdkLlmAdapter(BaseLlm)
                                    ├── HttpTransport / Transport Protocol
                                    └── OpenAIClient | AnthropicClient
                                          (config-driven: env vars for provider, model, endpoint)
```

### Modules

**1. LLM Client Abstraction (`backend/llm/`)**

A config-driven multi-provider abstraction layer. The package exposes a single abstract interface (`LLMClient`) with two provider implementations plus an ADK adapter:

| File | Purpose |
|------|---------|
| `protocol.py` | Abstract `LLMClient` interface + `Message`, `Usage`, `LLMResponse`, `LLMError` types. `generate_stream` yields `(text_delta, usage)` tuples so callers can observe usage mid-stream without mutating instance state. Pure Python, no framework coupling. |
| `transport.py` | `HttpTransport` — owns an `httpx.AsyncClient`, provides `send()` / `send_stream()`, wraps HTTP errors into `LLMError`. Also exposes a `Transport` Protocol that both `HttpTransport` and test fakes satisfy. Hoisted `_parse_error_body` from the duplicate implementations. |
| `anthropic.py` | `AnthropicClient` — delegates HTTP to a `Transport` instance; POSTs to `{base_url}/messages` (Anthropic messages format). Parses streaming SSE (`content_block_delta`). |
| `openai.py` | `OpenAIClient` — delegates HTTP to a `Transport` instance; POSTs to `{base_url}/chat/completions` (OpenAI format). Parses streaming SSE (`choices[...].delta.content`). |
| `factory.py` | `create_llm_client()` reads `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` from Settings / `.env` and returns the configured client. |
| `adk_adapter.py` | `AdkLlmAdapter(BaseLlm)` — bridges any `LLMClient` into Google ADK. Converts ADK `LlmRequest` → `Message[]`, calls the client, wraps the response as ADK `LlmResponse` with `usage_metadata` so ADK's tracing and observability see token counts. Accumulates `Usage` from stream tuples rather than reading `last_usage` post-stream. |

Provider selection is config-driven: `LLM_PROVIDER=openai` hits `/chat/completions`; `LLM_PROVIDER=anthropic` hits `/messages`. Each client accepts an optional `transport` parameter — when omitted a fresh `HttpTransport` is created with its own timeout. Tests inject a `FakeTransport` to avoid real HTTP calls.

`_parse_error_body` lives in `transport.py` as a shared utility rather than being duplicated across clients — the hoist keeps error-handling uniform.

The client is config-driven: `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, and `LLM_BASE_URL` are set via environment variables. Swapping providers is a config change, not a code change.

**2. Database Layer (`backend/db.py`)**

- `create_db_sessionmaker(database_url)` creates an async SQLAlchemy engine + sessionmaker lazily, rather than at import time
- `get_db(sessionmaker)` — FastAPI-compatible async generator dependency
- `init_db(database_url)` — creates the pgvector extension on startup, owning its own engine lifetime

**3. FastAPI Backend (`backend/`)**

Standard FastAPI application assembled via the `create_app()` factory with:
- `POST /api/chat` — mounted via `ag_ui_adk.add_adk_fastapi_endpoint()`, accepts AG-UI `RunAgentInput` (which includes the active corpus ID), invokes the ADK agent with corpus-scoped context, returns streaming AG-UI events over SSE
- `GET /api/corpora` — returns the list of available knowledge bases and their metadata: a persistent `id` (UUIDv4 used internally for DB scoping, MCP tool params, and chunk metadata), a `slug` (human-readable route segment, e.g. `/corpora/us-tax-code`, mutable), a `name` (display name shown on landing cards and headers, mutable), and a `description`
- `GET /api/health` — health check
- `GET /capabilities` — agent capability discovery (added by AG-UI middleware)
- `POST /agents/state` — experimental thread state retrieval (added by AG-UI middleware)
- Pydantic settings via `config.py` (reads `.env` for LLM config, Postgres credentials)
- Application assembly via `create_app(llm_client, settings)` factory with dependency injection — tests pass a `FakeLLMClient` directly, no import-time patching. The module-level `app = create_app()` preserves `fastapi dev` compatibility. A FastAPI lifespan handler closes transport connections on shutdown.

The `POST /api/chat` endpoint extracts the `corpus_id` from the incoming request and injects it into the ADK agent's session context, ensuring every tool call carries the active corpus identifier.

**4. RAG Pipeline (`rag/`)**

- Document chunking (recursive text splitter targeting ~500-token chunks with 50-token overlap)
- Each chunk includes metadata: `corpus_id`, title, source URL, and document reference
- Embedding via configurable embedding API (OpenAI-compatible client shape)
- Storage in PostgreSQL with pgvector `VECTOR(1536)` column and a `corpus_id` text column (indexed for fast filtering)
- Production: managed Supabase instance; development: local `pgvector/pgvector:pg18` Docker container
- IVFFlat index on the embedding column for fast cosine similarity search
- Query flow: embed user question → filter by `corpus_id = <active_corpus>` → `SELECT ... WHERE corpus_id = $corpus_id ORDER BY embedding <=> $query LIMIT 5` → return chunks as context
- Adding a new corpus is an ingestion and configuration task: run the seeding script for the new source documents with its `corpus_id`, register it in the corpus registry, and the frontend picks it up from `GET /api/corpora`

**5. MCP Server (`mcp_server/`)**

A Python MCP server using the official `mcp` SDK exposing:
- `search_knowledge(query: str, corpus_id: str, top_k: int = 5)` — semantic search over the RAG index, scoped to the given corpus
- `fetch_document(chunk_ids: list[str], corpus_id: str)` — retrieve full document chunks by ID, validated against the active corpus

Both tools accept and enforce a `corpus_id` parameter. The MCP server can run standalone (for testing with MCP Inspector or Claude Desktop) or embedded in the FastAPI process.

**6. Google ADK Agent System (`agents/`)**

Three specialist agents, each defined as an ADK `LlmAgent` and each operating within the active corpus:

- **Corpus Researcher:** "You search the active knowledge base for facts, dates, definitions, and specifications relevant to the user's question. Use the `search_knowledge` tool with the provided corpus ID. Report your findings with exact citations."
- **Corpus Critic:** "You review the Researcher's findings against the active corpus. Identify gaps, contradictions, weak citations, or missing context. Use `search_knowledge` for follow-up queries (always with the corpus ID) and `fetch_document` to read full chunks. Produce a critique with specific requests for clarification."
- **Corpus Synthesizer:** "You produce the final answer. Synthesize the Researcher's findings and the Critic's review into a concise, cited answer grounded in the active corpus. Structure: summary, key findings with citations, confidence assessment."

An ADK `SequentialAgent` orchestrates the flow: Researcher → Critic → Synthesizer. Each agent receives the previous agent's output and the active corpus ID in its context. The corpus ID is injected at the orchestration layer, not hardcoded in individual agents.

Agent thinking and intermediate results are streamed via ADK's built-in event system, which the AG-UI middleware converts to SSE events (`RUN_STARTED` → `TEXT_MESSAGE_START` → `TEXT_MESSAGE_CONTENT`* → `TEXT_MESSAGE_END` → `RUN_FINISHED`).

**7. SolidJS Frontend (`frontend/`)**

A Vite + SolidJS SPA with route-based corpus selection:

- **Landing page** (`/`): Introduces the product. Displays available knowledge bases as navigable cards showing the display name and description. Clicking a card navigates to `/corpora/<slug>`. The list is fetched from `GET /api/corpora` on load and can be updated by adding new corpus entries to the backend configuration.
- **Corpus route** (`/corpora/:slug`): Dedicated chat interface for the selected knowledge base. On mount, the frontend looks up the slug against the corpus list. If found, the corpus name is displayed prominently in the header and the UUID is used as `corpusId` in chat requests and conversation records. If the slug does not match any configured corpus, the route renders in-place with a friendly message explaining the corpus doesn't exist or its address has changed, alongside a button labeled "Browse available knowledge bases" that navigates to the landing page.
- **No in-chat corpus dropdown.** The active corpus is set by the route and cannot be changed mid-conversation.
- Chat input area (auto-growing textarea + submit and stop buttons)
- Streaming message display via user/assistant text bubbles
- Agent labels, tool call displays, and reasoning steps rendered in real-time as the multi-agent pipeline runs *(pending: integrated as part of the ADK agent frontend pipeline)*
- Cited answer blocks showing knowledge-base sources in the final response *(pending: depends on the ADK agent system returning citations in the output)*
- Agent status indicators (thinking / searching / synthesizing / done), shown per agent as the pipeline progresses *(pending: requires agent metadata in the AG-UI event stream)*
- Typing indicator (animated ellipsis) shown while the LLM is generating a response
- Error banner for LLM errors and localStorage quota warnings
- Conversation sidebar (left panel): lists all conversations for the current corpus by auto-generated title, newest first. Current conversation highlighted. Two-step delete confirmation (hover → trash icon → confirm/cancel). New conversation button at top. Mobile-responsive with an overlay backdrop.
- Conversation persistence via `localStorage` with per-conversation keys (`conversation:<uuid>`). `LS_LAST_OPENED` tracks the most recently active conversation. Data model: `{ id, corpusId, title, createdAt, messages[] }` — `corpusId` (UUIDv4) is included on every conversation record. When the user enters a corpus route (`/corpora/:slug`), the frontend resolves the slug to its UUID, loads all conversations from localStorage, and filters to those matching the resolved `corpusId`. Switching routes loads a different corpus's conversations — the persisted data is the same global key namespace, only the filter changes. This preserves the existing per-key localStorage persistence pattern while adding corpus awareness. Title auto-generated from first user message (~50 chars, word-bounded). `beforeunload` safety net ensures saves survive accidental navigation. LM Studio UI is the reference.
- Dark/light theme toggle, persisted in localStorage
- Tailwind CSS for styling (no component library dependency)

Connects to `POST /api/chat` via `@tanstack/ai-solid`'s `useChat` hook with `fetchServerSentEvents` adapter (AG-UI protocol over SSE). The `corpusId` is sent as part of the chat request from the route-level context.

**8. Deployment**

Two separate Docker images, each self-contained:
- **`multi-agent-rag-be`** (`backend/Dockerfile`): FastAPI + ADK + MCP + RAG on `python:3.13-slim`
- **`multi-agent-rag-fe`** (`frontend/Dockerfile`): multi-stage — Bun builds the SolidJS SPA, then Caddy serves it with `/api/*` reverse-proxied to the backend

Deployed via a two-service docker-compose on Coolify:
- `backend` — pulls `ghcr.io/olegedly/multi-agent-rag-be:latest`, internal port 8000
- `frontend` — pulls `ghcr.io/olegedly/multi-agent-rag-fe:latest`, internal port 80, with a persistent volume for Caddy TLS data

For local dev, `docker-compose.base.yml` + `docker-compose.dev-override.yml` spin up only a `pgvector/pgvector:pg18` database container (the production database is a managed Supabase instance — PostgreSQL with pgvector — not Docker). The backend runs natively via `uv run fastapi dev backend/main.py --port 8000` (hot-reload on save). The frontend runs via `bun run --cwd frontend dev` on the host (Vite HMR with `/api/*` proxy to `localhost:8000`). Both are orchestrated by `./dev.sh`.

**9. CI/CD Pipeline (`.github/workflows/deploy.yml`)**

GitHub Actions workflow triggered on pushes to `main` branch:

1. Build **both** images and push to GitHub Container Registry:
   - `ghcr.io/olegedly/multi-agent-rag-be:latest` — from `backend/Dockerfile`
   - `ghcr.io/olegedly/multi-agent-rag-fe:latest` — from `frontend/Dockerfile`
2. The frontend Dockerfile is self-contained: first stage builds the SPA with Bun, second stage serves it via Caddy. No frontend build step on the CI runner (only Docker is needed).
3. Coolify pulls the new images and redeploys. SSL and reverse proxy are handled by Coolify's edge proxy.

Pipeline: `git push` → GitHub Actions builds + pushes both images → Coolify pulls and redeploys. No manual SSH after initial setup.

### RAG Dataset

The knowledge base comprises multiple curated, authoritative, civilian-facing corpora. Each corpus is a standalone collection of documents on a specific domain, selected for accuracy, public accessibility, and clear structure.

Each corpus has three identifiers:
- A **persistent `corpus_id`** (UUIDv4) — used internally for DB scoping, MCP tool parameters, chunk metadata, and conversation records. This never changes once assigned.
- A **human-readable `slug`** — used in the URL (`/corpora/<slug>`) to provide clean, memorable routes. Mutable: changing the slug breaks existing bookmarks, which is acceptable collateral damage (handled gracefully — see below).
- A **`name`** — a human-readable display label shown on landing page cards, headers, and conversation context. Mutable independently of the slug.

Each corpus:
- Is independently ingestible via its own seeding script
- Carries a stable `corpus_id` (UUIDv4) assigned at ingestion time
- Is chunked and embedded into the shared pgvector store, with `corpus_id` on every chunk
- Is queried in isolation — retrieval is always filtered by the active `corpus_id`
- Is self-contained: conversations, citations, and evidence are drawn from that corpus alone

Documents within each corpus are pulled as markdown or text, chunked (~500-token chunks, 50-token overlap), embedded, and upserted into pgvector via per-corpus seeding scripts (`scripts/seed_<corpus_id>_knowledge_base.py`).

**Stale slug handling:** When a user navigates to a route whose slug does not match any configured corpus, the frontend does not force-redirect. Instead it renders the corpus route inline with an explanatory message — "This knowledge base doesn't exist or its address has changed" — and a button labeled "Browse available knowledge bases" that navigates to the landing page. This makes bookmark breakage a gentle, self-explanatory dead end rather than a confusing redirect.

### LLM Provider Strategy

The `LLMClient` abstraction (`backend/llm/`) supports both OpenAI and Anthropic message formats via a config-driven factory. `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, and `LLM_BASE_URL` are set via environment variables — swapping providers is a config change, not a code change.

The abstract interface encodes the *contract* (messages in → text+usage out), not a specific provider's SDK. `generate_stream` yields `(text_delta, usage)` tuples — usage is communicated through the return channel rather than through mutable instance state (`last_usage`), keeping the abstract seam pure.

Embedding follows the same pattern: a configurable embedding client will be added alongside the RAG pipeline.

### Observability

ADK's built-in tracing captures each agent's turns, tool calls, token usage, and latency. Traces are viewable through ADK's dev tools. No external observability service (Langfuse, etc.) is added at this stage.

## Testing Decisions

- **What makes a good test:** Test the external behaviour of each module through its public interface. Do not test implementation details, LLM output quality, or ADK internals. Mock the LLM client at its abstract interface boundary (`LLMClient`); only the concrete client tests mock at the HTTP wire level, because their request/response parsing is where real bugs live.
- **Stack:** `pytest` + `pytest-asyncio` + `pytest-httpx` (wire-level mock, transport module only).
- **Transport seam:** HTTP is abstracted behind a `Transport` protocol. Production code uses `HttpTransport`; tests use `FakeTransport` (no HTTP mocking library needed outside the transport's own tests).
- **DI seam:** `backend/main.py` exposes a `create_app(llm_client)` factory. Tests call `create_app(llm_client=FakeLLMClient())` — no module reassignment, no import-order footguns.
- **Database:** None. All tests are pure unit tests with no Docker or pgvector dependency.
- **Test layout:** Parallel to `backend/` at `tests/`, keeping test code out of Docker images and navigation noise free.

### What is tested

| Module | How | What it covers |
|---|---|---|
| `frontend/.../title.ts` | `generateTitle` pure function | Empty string, whitespace, word-boundary truncation, trailing-punctuation trimming, single-word edge cases — 8 tests |
| `frontend/.../useChatStore` (store.ts) | `createConversationStore` | Auto-creation, localStorage CRUD, switch/delete/create, corrupt-data tolerance, last-conversation auto-create — 9 tests |
| `frontend/.../Sidebar.tsx` | `render` + `fireEvent` | Renders list, highlights current, empty state, onNew/onSelect callbacks, trash buttons per row, confirm/cancel hidden on mount — 7 tests |
| `frontend/.../ChatView.tsx` | `render` + `createSignal` mocks | Message rendering, send/stop buttons, disabled-during-loading, error banner, storage error dismiss, typing indicator logic — 11 tests |
| `frontend/.../deriveTitle` (useChatStore internals) | Pure-function inline | First-user-message extraction from `UIMessage[]`, multi-part text, no-text-parts, truncation, whitespace fallback — 9 tests |
| `frontend/.../useChatErrorPropagation` (resilientFetch) | Live `useChat` hook + `fetchServerSentEvents` | Non-ok HTTP response triggers error path via resilientFetch; RUN_ERROR event surfaces to `chat.error`; no silent swallow — 12 tests |

Frontend tests: **56 tests across 6 files**, all passing. Runs in CI.

| Module | How | What it covers |
|---|---|---|
| `backend/llm/protocol.py` | Pure-data assertions | `Message`, `Usage`, `LLMResponse`, `LLMError` construction; abstract class guard |
| `backend/llm/transport.py` | `pytest-httpx` | `send` and `send_stream` return/error behaviour, `_parse_error_body` edge cases, `close` idempotency |
| `backend/llm/openai.py` | `FakeTransport` | Request body shape (system→messages[0]), SSE deltas, `[DONE]`, usage from final chunk, 4xx→`LLMError` |
| `backend/llm/anthropic.py` | `FakeTransport` | Request body shape (system in separate field), SSE events (`content_block_delta`, `message_start`, `message_delta`), error handling |
| `backend/llm/factory.py` | Fixture-based env override | Returns `OpenAIClient`/`AnthropicClient` by provider; `ValueError` on unknown |
| `backend/llm/adk_adapter.py` | `FakeLLMClient` + real ADK types | `LlmRequest`→`Message[]` conversion, streaming deltas, usage metadata, system instruction extraction, function-call parts |
| `backend/config.py` | Fixture-based env override | Defaults, `database_url` property, `extra='ignore'` |
| `backend/main.py` | `create_app(llm_client=FakeLLMClient())` + `TestClient` | `GET /api/health` returns 200 JSON; `POST /api/chat` returns 200 |

### Modules not yet tested

`rag/`, `mcp_server/`, and `agents/` don't exist in the codebase yet. Their tests will be added when those modules are implemented, following the same approach: mock at the abstract boundary, pure unit tests, no database dependency for business logic.

The following corpus-scoped tests are planned:

| Module | How | What it covers |
|---|---|---|
| `frontend/.../routes.ts` | `render` + route simulation | Landing page renders corpus cards; `/corpora/:slug` resolves slug to corpus UUID; unknown slug redirects to landing page with message; route change filters conversation list by corpus — 7 tests |
| `rag/retriever.py` | Mock embedding client + in-memory chunk store | `retrieve(query, corpus_id=A)` returns only chunks from corpus A; omitting corpus_id raises; empty corpus returns empty results — 4 tests |
| `mcp_server/tools.py` | `FakeRetriever` | `search_knowledge` with corpus_id returns scoped results; `search_knowledge` without corpus_id raises `ValueError`; `fetch_document` with mismatched corpus_id returns empty — 4 tests |
| `agents/orchestrator.py` | `FakeLLMClient` + mock tools | Corpus ID propagates from orchestrator to each agent's tool calls; cross-corpus leakage returns no results; conversation context includes active corpus identifier — 4 tests |
| `backend/main.py` | `TestClient` | `GET /api/corpora` returns corpus list with expected shape; corpus ID round-trips through chat endpoint — 2 tests |

## Out of Scope

- **Blended cross-corpus retrieval.** Retrieval always operates within a single corpus. The architecture does not support queries that span multiple corpora simultaneously.
- **Corpus switching mid-conversation.** A conversation is bound to the corpus it was started in. To explore a different knowledge base, the user returns to the landing page and starts a new conversation.
- **In-chat corpus dropdown or selector.** Corpus selection is route-based only.
- **Cross-corpus conversation switching at the route level.** Conversations from different corpora live in the same localStorage store, but the UI never shows conversations from more than one corpus at once — the route controls which corpus is active, and the conversation list is filtered accordingly.
- **Slug immutability guarantees.** Slugs are mutable. Renaming a slug may break bookmarks; the frontend handles stale slugs with a graceful redirect to the landing page.
- Production user authentication (the demo is open-access; auth can be added later per client requirements). Token abuse prevention is handled via rate-limiting (see Further Notes).
- Multi-tenancy or per-user RAG indexes
- Fine-tuning any LLM
- Pinecone or any non-pgvector vector store
- Hybrid search or reranking (pure vector similarity is sufficient for the use case)
- LangChain, LangGraph, or any non-ADK orchestration framework
- n8n, Make, Zapier, or any automation platform integration
- Next.js, Vercel, or any SSR framework
- Langfuse or external observability service (ADK tracing is sufficient for demo purposes)
- Mobile app or native client
- Complex multi-environment CI/CD (staging, production, rollbacks)
- User feedback scoring or evaluation datasets

## Further Notes

This project has dual value:

1. **Skill building:** Every module teaches a production skill that maps directly to Upwork job requirements — FastAPI, Pydantic, pgvector, MCP, ADK, SSE streaming, Docker deployment.

2. **Proposal leverage:** The live demo URL is the centerpiece of every proposal. The pitch: *"I built a multi-agent research system with route-based corpus selection — users land on a dashboard, pick a curated knowledge base, and ask questions that three specialist agents answer by searching only that corpus. MCP tools, pgvector retrieval, real-time streaming, fully Dockerized. Here's a link. Pick a corpus and try it."*

### Token Abuse Prevention

The demo is public and unauthenticated. Without protection, a malicious actor could exhaust the DeepSeek API budget through repeated requests. Mitigations:

1. **IP-based rate limiting** via Caddy (or Nginx) at the reverse proxy layer: max 10 requests per IP per minute, burst up to 20. This is configured in the Caddyfile / Nginx config, not in application code.
2. **Daily token budget** enforced at the FastAPI middleware layer: a hard cap on total LLM tokens consumed per day. When the budget is exhausted, all subsequent requests return `429 Too Many Requests` with a message like "Daily demo budget reached. Try again tomorrow." The budget is stored in a simple file on the VPS (no database needed).
3. **Query length limit** enforced by Pydantic: max 500 characters per question. Longer inputs are rejected at the API boundary.

These are demo-grade mitigations — sufficient to deter casual abuse without the complexity of real authentication. If a client wants production security, they pay for it.

The market-validated posting that this demo directly addresses:

> "Create AI agents (3 to 4) and an MCP server with Tools registered. 3 agents using Google and 1 agent using Crew.AI. Need to prove how these agents can communicate via MCP server. Use a small public dataset and build a search to lookup in local dataset and then send to LLM via API call."

Substitute Google ADK for Crew.AI, add multiple curated corpora with route-based selection, and the spec is a direct match.
