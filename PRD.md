# PRD: Multi-Agent RAG Research System (Portfolio Demo)

## Problem Statement

Organizations across the public and private sectors need intelligent research systems that can answer questions grounded in authoritative, curated knowledge — not sprawling web searches or unverified AI hallucinations. From compliance officers querying regulatory libraries to policy researchers navigating institutional archives, the demand for **grounded, cited, real-time research assistance** over well-defined knowledge bases is growing fast.

Building such a system requires mastery of the modern AI engineering stack:

1. Production FastAPI backends with Pydantic
2. RAG with PostgreSQL + pgvector
3. MCP servers as tool interfaces
4. Multi-agent orchestration with LangChain
5. Real-time streaming agent output to a web UI
6. Containerized, deployable full-stack applications
7. Route-based, corpus-scoped retrieval across multiple curated knowledge bases

This project demonstrates all of the above in a single, deployable system: a multi-agent research assistant that serves grounded, cited answers from multiple curated public knowledge bases — each a first-class destination with its own route, its own corpus, and its own conversations via a LangChain pipeline streamed over SSE.

## Solution

An interactive multi-agent research system where:

- A landing page introduces the system and lists the available curated knowledge bases
- Selecting a knowledge base navigates to a dedicated route for that corpus
- The user submits a research question within the context of that corpus
- Three specialist agents (Researcher, Critic, Synthesizer) collaborate via a LangChain pipeline to answer it
- Agents search only the active corpus in a pgvector knowledge base — retrieval is scoped by `corpus_id`
- The entire reasoning process streams to the dashboard in real-time — tool calls, intermediate findings, final synthesis
- The system is config-driven: LLM provider, model, and API endpoint are environment variables
- The frontend is a Vite + SolidJS SPA served as static files, connecting to the backend via `@tanstack/ai-solid`'s `useChat` hook over SSE
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
17. As the developer, I want LangSmith tracing instrumented on all agent calls, so that I can debug and demonstrate observability awareness.
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
SolidJS SPA ──SSE──▶ FastAPI ──▶ LangGraph Multi-Agent Pipeline
  (@tanstack/ai-solid,    (create_app()    └── Researcher → Critic → Synthesizer
                              │
                              ├── MCP Server (standalone, for pi/Claude Desktop)
                              │         └── pgvector RAG (corpus-filtered)
                              │               └── PostgreSQL ── chunks with corpus_id
                              │
                              └── LangChain ChatOpenAI / ChatAnthropic
                                    ├── Config-driven: env vars for provider, model, endpoint
                                    └── corpus_id baked into @tool closures at factory time
```

### Modules

**1. LLM Layer**

LangChain's `ChatOpenAI` (or `ChatAnthropic` for Claude) handles model interaction. The provider, model name, API key, and base URL are configured via environment variables (`LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`) read by Pydantic `Settings` — swapping providers is a config change, not a code change.

**2. Database Layer (`backend/db.py` + `backend/models.py`)**

- `create_db_sessionmaker(database_url)` creates an async SQLAlchemy engine + sessionmaker lazily, rather than at import time
- `get_db(sessionmaker)` — FastAPI-compatible async generator dependency
- `init_db(database_url)` — creates the pgvector extension on startup, owning its own engine lifetime
- `Document` table: `id` (PK), `corpus_id` (TEXT, indexed), `content` (TEXT), `embedding` (VECTOR(768)), `metadata` (JSONB with title, source URL, chunk_index). IVFFlat index on the embedding column.
- `document_sources` table: `corpus_id`, `filename`, `content_hash` (SHA-256), `updated_at` — used by the seeding script for idempotency diffs (skip unchanged, update changed, delete removed)

**3. FastAPI Backend (`backend/`)**

Standard FastAPI application assembled via the `create_app()` factory with:
- `POST /api/chat/{slug}` — raw SSE streaming endpoint that resolves the corpus slug to a UUID via `CorporaConfig.get(slug)`, creates a LangChain agent with corpus-scoped RAG tools, and streams the agent's response as AG-UI protocol events via the `ag-ui-protocol` Python SDK (`EventEncoder`). Corpus routing is URL-based, eliminating state-propagation issues.
- `GET /api/corpora` — returns the list of available knowledge bases and their metadata: a persistent `id` (UUIDv4 used internally for DB scoping, MCP tool params, and chunk metadata), a `slug` (human-readable route segment, e.g. `/api/chat/us-tax-code`, mutable), a `name` (display name shown on landing cards and headers, mutable), and a `description`
- `GET /api/health` — health check
- Pydantic settings via `config.py` (reads `.env` for LLM config, Postgres credentials)
- Application assembly via `create_app(settings, corpora_config)` factory with dependency injection — tests pass fakes directly, no import-time patching. The module-level `app = create_app()` preserves `fastapi dev` compatibility.
- `ChatGuard` middleware for token budget enforcement and query validation

The `POST /api/chat/{slug}` endpoint looks up the corpus slug via `CorporaConfig.get(slug)`, injects the resolved `corpus_id` into the tool factory (`create_rag_tools(corpus_id=...)`), and streams the pipeline result. The corpus ID is baked into LangChain `@tool` closures — the LLM never sees it, preventing retrieval-scope contamination.

**4. Embedding Client (`backend/embeddings/`)**

Mirrors the LLM client pattern: abstract `EmbeddingClient` protocol (`embed_texts`), concrete `OpenRouterEmbeddingClient` (OpenAI-compatible `POST /v1/embeddings` via `HttpTransport`), config-driven factory. Uses Qwen3 Embedding via OpenRouter with MRL set to `dimensions: 768`. Config env vars: `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_DIMENSIONS`.

**5. Chunker Registry (`backend/rag/chunker.py`)**

Per-corpus strategy selection rather than one algorithm for all documents:
- `MarkdownHeadingChunker` — splits on markdown headings (`#`/`##`/`###`), then recursively to ~500 tokens. Best for technical docs, API references.
- `ParagraphChunker` — splits on double-newlines, merges small paragraphs up to target size. Best for legal or dense prose.
- `RecursiveChunker` — character-based fallback splitting by separator priority. Best for unstructured text.
- `FixedSizeChunker` — mechanical token count with overlap.

Each chunk targets ~500 tokens with 50-token overlap. The strategy is configured per corpus in the YAML registry.

**6. Corpus Registry (`backend/corpora.yaml`)**

A human-editable YAML file committed to the repo and `COPY`'d into the Docker image. Defines available corpora with their identifiers, display metadata, and chunker strategy:

```yaml
corpora:
  - id: "315e41aa-8657-46c0-ac4b-ea4355babf0a"    # stable UUIDv4
    slug: "eu-ai-act"
    name: "EU AI Act"
    description: "European Union Artificial Intelligence Act — full regulation text"
    chunker: "markdown-heading"
    documents: "corpora/eu-ai-act/**/*.md"
```

Read once on `create_app()` startup. Exposed via `GET /api/corpora`.

**7. RAG Query Layer (`backend/rag/search.py`)**

- Embed the user question via the embedding client
- Cosine similarity search: `SELECT 1 - (embedding <=> :query_vec) AS score WHERE corpus_id = :corpus_id ORDER BY embedding <=> :query_vec LIMIT :top_k`
- Returns typed `SearchResult` objects (id, corpus_id, content, metadata, score) where score = `1 - cosine_distance`, range [0,1], higher = better
- Companion `read_document(chunk_ids, corpus_id)` returns all chunks from the same source file(s) (source-level fetch), enabling the Critic agent to verify citations with full context
- Storage: pgvector `VECTOR(768)` column with IVFFlat index. Production: managed Supabase. Dev: local `pgvector/pgvector:pg18` Docker container.
- Adding a new corpus is an ingestion and configuration task: add its entry to `corpora.yaml`, place documents in `corpora/<slug>/`, run the seeding script, and the frontend picks it up from `GET /api/corpora`

**8. MCP Server (`backend/mcp_server/`)**

A standalone Python MCP server (official `mcp` SDK, stdio transport) exposing two corpus-scoped tools:
- `search_corpus(query: str, corpus_id: str, top_k: int = 5)` — semantic search over the RAG index, scoped to the given corpus. Returns chunks with cosine similarity scores (1 - distance, range [0,1]).
- `read_document(chunk_ids: list[int], corpus_id: str)` — source-level document retrieval. Given chunk IDs from a search result, returns all chunks from the same source file(s) for full-context citation verification.

Both tools accept and enforce a `corpus_id` parameter. Missing or unknown `corpus_id` returns a structured error (not an exception). Errors are returned as dicts, not raised — the agent always gets a parseable response. The server wraps the RAG query interface directly (no HTTP).

**Standalone mode:** `uv run python -m backend.mcp_server` for MCP Inspector or Claude Desktop. The server is **not** embedded in the FastAPI process — the LangChain pipeline tools and the MCP server both import the same functions from `backend/rag/search.py`.

**9. LangChain Agent Pipeline (`backend/agents/`)**

A three-agent pipeline orchestrated via a LangGraph ``StateGraph(MultiAgentState)`` with an explicit tool-calling loop (``backend/agents/graph_orchestrator.py``). Each agent drives the model directly in a loop — streaming output, executing tool calls, feeding results back, and producing a final answer with proper reasoning-block boundaries.

- **Corpus Researcher:** An agent with ``rag_search`` and ``rag_read_document`` tools. Scoped to the active corpus via a tool factory that bakes the corpus UUID into each tool's closure — the LLM never sees the UUID. The agent searches the knowledge base for facts, dates, definitions, and specifications relevant to the user's question, and returns its findings with exact citations (max 4 tool calls).
- **Corpus Critic:** An agent with ``rag_search`` and ``rag_read_document`` tools. Reviews the Researcher's findings for gaps, contradictions, weak citations, or missing context using independent verification. Produces a structured critique with verified claims, concerns, and suggested improvements (max 4 tool calls).
- **Corpus Synthesizer:** An agent with **no tools** — reads everything from the accumulating conversation context. Synthesizes the Researcher's findings and the Critic's review into a final answer: summary, key findings with plain-text citations, confidence assessment.

**Tools** are defined via the `@tool` decorator from `langchain_core.tools`. `create_rag_tools(corpus_id, ...)` returns two LangChain `BaseTool` objects:
- `rag_search(query, top_k)` — semantic vector search over the active corpus
- `rag_read_document(chunk_ids)` — retrieve full source context for given chunk IDs

Both tools accept only the parameters the LLM should control (`query`, `top_k`, `chunk_ids`). The `corpus_id` is baked into the closure at factory time, ensuring retrieval-scope isolation without depending on session-state plumbing.

The RAG query functions themselves live in `backend/rag/search.py` — the single source of truth shared by both the LangChain tools and the standalone MCP server.

**SSE streaming format:** The pipeline emits AG-UI protocol events via the `ag-ui-protocol` Python SDK. Pydantic event models (`RunStartedEvent`, `TextMessageStartEvent`, `TextMessageContentEvent`, `TextMessageEndEvent`, `RunFinishedEvent`, `RunErrorEvent`) are converted to SSE by `EventEncoder.encode()`, which produces camelCase JSON in `data: {...}\n\n` format. The event sequence is:
```
RUN_STARTED → TEXT_MESSAGE_START → TEXT_MESSAGE_CONTENT → TEXT_MESSAGE_END → RUN_FINISHED
```
The `thread_id` and `run_id` are extracted from the TanStack AI request body (`body.threadId`, `body.runId`). Extra fields like `finishReason` and `usage` ride along on `RunFinishedEvent` via Pydantic's `extra="allow"` passthrough. The legacy `[DONE]` sentinel has been removed — `RUN_FINISHED` serves as the termination signal. The frontend's `@tanstack/ai-solid` `useChat` hook parses this format natively via `StreamProcessor.processChunk()`, which dispatches on AG-UI event types.

**10. SolidJS Frontend (`frontend/`)**

A Vite + SolidJS SPA with route-based corpus selection using `@solidjs/router`:

- **Landing page** (`/`): Introduces the product. Displays available knowledge bases as navigable cards showing the display name and description. Clicking a card navigates to `/corpora/<slug>`. The list is fetched once from `GET /api/corpora` at the app root and cached globally via SolidJS context (no re-fetch on route changes). Updated by adding new corpus entries to the backend's `corpora.yaml`.
- **Corpus route** (`/corpora/:slug`): Dedicated chat interface for the selected knowledge base. On mount, the frontend looks up the slug against the corpus list. If found, the corpus name is displayed prominently in the header and the UUID is used as `corpusId` in chat requests and conversation records. If the slug does not match any configured corpus, the route renders in-place with a friendly message explaining the corpus doesn't exist or its address has changed, alongside a button labeled "Browse available knowledge bases" that navigates to the landing page.
- **No in-chat corpus dropdown.** The active corpus is set by the route and cannot be changed mid-conversation.
- Chat input area (auto-growing textarea + submit and stop buttons)
- Streaming message display via user/assistant text bubbles
- Agent labels (🔍 Researcher, ⚖️ Critic, 📝 Synthesizer), tool call displays, and reasoning steps rendered in real-time as the multi-agent pipeline runs
- Typing indicator (animated ellipsis) shown while the LLM is generating a response
- Error banner for LLM errors and localStorage quota warnings
- Conversation sidebar (left panel): lists all conversations for the current corpus by auto-generated title, newest first. Current conversation highlighted. Two-step delete confirmation (hover → trash icon → confirm/cancel). New conversation button at top. Mobile-responsive with an overlay backdrop.
- Conversation persistence via `localStorage` with per-conversation keys (`conversation:<uuid>`). `LS_LAST_OPENED` tracks the most recently active conversation. Data model: `{ id, corpusId, title, createdAt, messages[] }` — `corpusId` (UUIDv4) is included on every conversation record. When the user enters a corpus route (`/corpora/:slug`), the frontend resolves the slug to its UUID, loads all conversations from localStorage, and filters to those matching the resolved `corpusId`. Switching routes loads a different corpus's conversations — the persisted data is the same global key namespace, only the filter changes. This preserves the existing per-key localStorage persistence pattern while adding corpus awareness. Title auto-generated from first user message (~50 chars, word-bounded). `beforeunload` safety net ensures saves survive accidental navigation. LM Studio UI is the reference.
- Dark/light theme toggle, persisted in localStorage
- Tailwind CSS for styling (no component library dependency)

Connects to `POST /api/chat/{slug}` via `@tanstack/ai-solid`'s `useChat` hook with `fetchServerSentEvents` adapter (TanStack AI SSE protocol). The corpus slug is part of the URL path — no corpus UUID is sent in the request body.

**11. Seeding Script (`scripts/seed_knowledge_base.py`)**

A standalone CLI script that populates the vector database from source documents. Idempotent: computes SHA-256 of each file, compares against the `document_sources` table, and applies a diff (insert new, update changed, delete removed, skip unchanged). Usage: `uv run scripts/seed_knowledge_base.py --corpus <slug>` or `--all` for every configured corpus.

Run once per corpus on first deploy. On subsequent deploys, the hash-based diff makes it instant unless source files changed. Run in production as a Coolify post-deployment command inside the backend container.

**12. Deployment**

Two separate Docker images, each self-contained:
- **`multi-agent-rag-be`** (`backend/Dockerfile`): FastAPI + LangChain + MCP + RAG on `python:3.13-slim`. Also `COPY`s `corpora/` and `scripts/` into the image so the seeding script has access to source documents.
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
- A **human-readable `slug`** — used in the URL (`/api/chat/<slug>`) to provide clean, memorable routes. Mutable: changing the slug breaks existing bookmarks, which is acceptable collateral damage (handled gracefully — see below).
- A **`name`** — a human-readable display label shown on landing page cards, headers, and conversation context. Mutable independently of the slug.

Each corpus:
- Is independently ingestible via a single generalized seeding script
- Carries a stable `corpus_id` (UUIDv4) assigned at ingestion time
- Is chunked according to its configured strategy (`markdown-heading`, `paragraph`, or `recursive`)
- Is embedded via Qwen3 Embedding (768-dim, MRL) through OpenRouter
- Is stored in the shared pgvector store with `corpus_id` on every chunk
- Is queried in isolation — retrieval is always filtered by the active `corpus_id`
- Is self-contained: conversations, citations, and evidence are drawn from that corpus alone

Documents within each corpus are pulled as markdown or text, chunked (~500-token chunks, 50-token overlap), embedded, and upserted into pgvector via a single seeding script (`scripts/seed_knowledge_base.py --corpus <slug>`).

**Stale slug handling:** When a user navigates to a route whose slug does not match any configured corpus, the frontend does not force-redirect. Instead it renders the corpus route inline with an explanatory message — "This knowledge base doesn't exist or its address has changed" — and a button labeled "Browse available knowledge bases" that navigates to the landing page. This makes bookmark breakage a gentle, self-explanatory dead end rather than a confusing redirect.

### LLM Provider Strategy

LangChain's model classes handle provider abstraction. The `langchain-openai` package's `ChatOpenAI` works with any OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, etc.), and `langchain-anthropic`'s `ChatAnthropic` handles Anthropic/Claude. The provider, model, API key, and base URL are set via environment variables (`LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`) read by Pydantic `Settings` — swapping providers is a config change, not a code change.

### Embedding Provider Strategy

The `EmbeddingClient` abstraction (`backend/embeddings/`) mirrors the LLM pattern: an abstract protocol (`embed_texts`), a concrete implementation (`OpenRouterEmbeddingClient` via OpenAI-compatible `POST /v1/embeddings`), and a config-driven factory. Uses Qwen3 Embedding at 768 dimensions (MRL) through OpenRouter. The `HttpTransport` seam from the LLM layer is reused for HTTP.

Config env vars: `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_DIMENSIONS`. Swapping embedding providers is a config change, not a code change — same principle as the LLM layer.

### Observability

LangSmith traces each agent's turns, tool calls, token usage, and latency. `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true` are set via environment variables. No external observability service (Langfuse, etc.) is added at this stage.

## Testing Decisions

- **What makes a good test:** Test the external behaviour of each module through its public interface. Do not test implementation details, LLM output quality, or LangChain internals. Mock the database and embedding client at their abstract boundaries; only the concrete client tests mock at the HTTP wire level.
- **Stack:** `pytest` + `pytest-asyncio` + `pytest-httpx`.
- **DI seam:** `backend/main.py` exposes a `create_app(settings, corpora_config)` factory. Tests pass fakes via injection — no module reassignment, no import-order footguns.
- **Database:** None. All tests are pure unit tests with no Docker or pgvector dependency.
- **Tool testability:** The `create_rag_tools(corpus_id, sessionmaker, embedding_client)` factory accepts optional fakes for both the DB session and embedding client — tests inject `FakeSessionMaker` and `FakeEmbeddingClient` instead of patching imports.
- **Test layout:** Parallel to `backend/` at `tests/`, keeping test code out of Docker images and navigation noise free.

### What is tested

Frontend tests: pure-function tests for title generation, conversation store CRUD, component rendering (Sidebar, ChatView), stream error propagation, tool result formatting, and message grouping. Runs in CI.

Backend tests: chunker strategies (heading/paragraph/recursive/fixed-size), corpus-scoped search, `read_document` full-context retrieval, config validation, corpus config parsing (YAML, duplicates, slug resolution), middleware (budget read/write/exhaust, query validation), LangChain tool factory (shape, scoping, cross-corpus isolation), pipeline AG-UI event sequencing (RunStarted/TextMessage/ToolCall/RunFinished), SSE endpoint integration, seed script idempotency (insert/update/delete), MCP server tool shape and error handling, embedding factory, and ORM model constraints/indexes. All pure unit tests with no Docker or DB dependency.

### Modules not yet created (planned)

| Module | What it covers |
|---|---|
| `frontend/.../LandingPage.tsx` | Landing page renders corpus cards; slug resolution; unknown slug handling; route-based conversation filtering (tracked in [#26](https://github.com/olegedly/multi-agent-rag/issues/26)) |

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
- LangChain (beyond `create_agent`), Crew.AI, or any non-LangChain orchestration framework
- n8n, Make, Zapier, or any automation platform integration
- Next.js, Vercel, or any SSR framework
- Langfuse or external observability service (LangSmith tracing is sufficient for demo purposes)
- Mobile app or native client
- Complex multi-environment CI/CD (staging, production, rollbacks)
- User feedback scoring or evaluation datasets

## Further Notes

This project has dual value:

1. **Skill building:** Every module teaches a production skill that maps directly to Upwork job requirements — FastAPI, Pydantic, pgvector, MCP, LangChain, SSE streaming, Docker deployment.

2. **Proposal leverage:** The live demo URL is the centerpiece of every proposal. The pitch: *"I built a multi-agent research system with route-based corpus selection — users land on a dashboard, pick a curated knowledge base, and ask questions that three specialist agents answer by searching only that corpus. MCP tools, pgvector retrieval, real-time streaming, fully Dockerized. Here's a link. Pick a corpus and try it."*

### Token Abuse Prevention

The demo is public and unauthenticated. Without protection, a malicious actor could exhaust the DeepSeek API budget through repeated requests. Mitigations:

1. **IP-based rate limiting** via Caddy (or Nginx) at the reverse proxy layer: max 10 requests per IP per minute, burst up to 20. This is configured in the Caddyfile / Nginx config, not in application code.
2. **Daily token budget** enforced at the FastAPI middleware layer: a hard cap on total LLM tokens consumed per day. When the budget is exhausted, all subsequent requests return `429 Too Many Requests` with a message like "Daily demo budget reached. Try again tomorrow." The budget is stored in a simple file on the VPS (no database needed).
3. **Query length limit** enforced by Pydantic: max 500 characters per question. Longer inputs are rejected at the API boundary.

These are demo-grade mitigations — sufficient to deter casual abuse without the complexity of real authentication. If a client wants production security, they pay for it.

The market-validated posting that this demo directly addresses:

> "Create AI agents (3 to 4) and an MCP server with Tools registered. 3 agents using Google and 1 agent using Crew.AI. Need to prove how these agents can communicate via MCP server. Use a small public dataset and build a search to lookup in local dataset and then send to LLM via API call."

Substitute LangChain for Crew.AI, add multiple curated corpora with route-based selection, and the spec is a direct match.
