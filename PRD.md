# PRD: Multi-Agent RAG Research System (Portfolio Demo)

## Problem Statement

I am an experienced full-stack developer and frontend specialist entering the AI engineering freelance market on Upwork. My research (~150 real postings, June 2026) confirms that the highest-value, lowest-competition niche is **MCP orchestration + multi-agent systems + RAG** — clients explicitly post jobs for "agents + MCP server + RAG + inter-agent communication." However, I have no shipped portfolio piece in this space. I need a single demonstrable project that proves I can:

1. Build production FastAPI backends with Pydantic
2. Implement RAG with PostgreSQL + pgvector
3. Build MCP servers as tool interfaces
4. Orchestrate multi-agent systems with Google ADK
5. Stream real-time agent output to a web UI
6. Containerize and deploy the full stack

Without this demo, every proposal is a promise. With it, every proposal includes a live link.

## Solution

An interactive multi-agent research system where:

- A user submits a research question via a web dashboard
- Three specialist AI agents (Researcher, Critic, Synthesizer) collaborate via ADK to answer it
- Agents search a pgvector knowledge base (RAG over the MCP specification + ADK documentation)
- The entire reasoning process streams to the dashboard in real-time — tool calls, intermediate findings, final synthesis
- The system is config-driven: LLM provider, model, and API endpoint are environment variables
- The frontend is a Vite + SolidJS SPA served as static files, connecting to the backend via `@tanstack/ai-solid`'s `useChat` hook over the AG-UI protocol
- The system is Dockerized for deployment, with a native `fastapi dev` workflow for local development

The demo is **self-referential**: it uses ADK + MCP to answer questions about ADK + MCP. This signals deep domain competence to potential clients.

## User Stories

1. As a visitor to the demo, I want to type a natural-language research question into a web dashboard, so that I can see how the system handles my query.
2. As a visitor, I want to see each agent's reasoning and tool calls streamed in real-time, so that I understand the multi-agent collaboration process.
3. As a visitor, I want the final answer to include citations from the knowledge base, so that I trust the output is grounded and not hallucinated.
4. As a potential client, I want to query the system about MCP or ADK topics, so that I can assess the depth of relevant domain knowledge.
5. As a potential client, I want to see the system deployed at a live URL, so that I can evaluate it without running any code.
6. As a potential client, I want to see clean, production-quality code in a public repository, so that I can evaluate engineering practices.
7. As the developer, I want the LLM client to be abstracted behind a single interface that supports both OpenAI-format and Anthropic-format endpoints, so that I can explain to future clients that adapting to their preferred provider is a configuration change (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`), not a rewrite.
8. As the developer, I want the RAG pipeline to use pgvector for semantic search, so that I can demonstrate vector database skills.
9. As the developer, I want the MCP server to be independently runnable and testable, so that I can reuse it in future projects.
10. As the developer, I want the system to run in Docker Compose with a single command, so that deployment is reproducible.
11. As the developer, I want ADK tracing instrumented on all agent calls, so that I can debug and demonstrate observability awareness.
12. As a user, I want the dashboard to persist my conversation history in browser localStorage, so that I can return to previous research sessions without losing context.
13. As a user, I want each conversation to show an auto-generated title based on the first user message, so that I can identify conversations at a glance.
14. As a user, I want a sidebar listing all my past conversations, so that I can switch between them easily.
15. As a user, I want to delete individual conversations from the sidebar, so that I can clean up old sessions.
16. As a user, I want to start a new conversation without losing my existing ones, so that I can explore multiple research topics.
17. As the developer, I want the frontend to be a vanilla SPA (no Next.js, no Vercel) served as static files, so that I retain full deployment flexibility.

## Implementation Decisions

### Architecture Overview

```
SolidJS SPA ──AG-UI/SSE──▶ FastAPI ──▶ Google ADK Orchestrator
  (@tanstack/ai-solid,     (create_app()    ├── Agent A (Researcher)
   fetchServerSentEvents)   factory)        ├── Agent B (Critic)
                                              └── Agent C (Synthesizer)
                              │
                              ├── MCP Server (search_knowledge, fetch_document)
                              │         └── pgvector RAG
                              │               └── PostgreSQL
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
- `POST /api/chat` — mounted via `ag_ui_adk.add_adk_fastapi_endpoint()`, accepts AG-UI `RunAgentInput`, invokes the ADK agent, returns streaming AG-UI events over SSE
- `GET /api/health` — health check
- `GET /capabilities` — agent capability discovery (added by AG-UI middleware)
- `POST /agents/state` — experimental thread state retrieval (added by AG-UI middleware)
- Pydantic settings via `config.py` (reads `.env` for LLM config, Postgres credentials)
- Application assembly via `create_app(llm_client, settings)` factory with dependency injection — tests pass a `FakeLLMClient` directly, no import-time patching. The module-level `app = create_app()` preserves `fastapi dev` compatibility. A FastAPI lifespan handler closes transport connections on shutdown.

**4. RAG Pipeline (`rag/`)**

- Document chunking (recursive text splitter targeting ~500-token chunks with 50-token overlap)
- Embedding via configurable embedding API (OpenAI-compatible client shape)
- Storage in PostgreSQL with pgvector `VECTOR(1536)` column
- Production: managed Supabase instance; development: local `pgvector/pgvector:pg18` Docker container
- IVFFlat index on the embedding column for fast cosine similarity search
- Query flow: embed user question → `SELECT ... ORDER BY embedding <=> $query LIMIT 5` → return chunks as context

**5. MCP Server (`mcp_server/`)**

A Python MCP server using the official `mcp` SDK exposing:
- `search_knowledge(query: str, top_k: int = 5)` — semantic search over the RAG index
- `fetch_document(chunk_ids: list[str])` — retrieve full document chunks by ID

Both tools are thin wrappers over the RAG pipeline. The MCP server can run standalone (for testing with MCP Inspector or Claude Desktop) or embedded in the FastAPI process.

**6. Google ADK Agent System (`agents/`)**

Three specialist agents, each defined as an ADK `LlmAgent`:

- **Agent A (Researcher):** "You search the knowledge base for facts, dates, definitions, and specifications relevant to the user's question. Use the `search_knowledge` tool. Report your findings with exact citations."
- **Agent B (Critic):** "You review Agent A's findings. Identify gaps, contradictions, weak citations, or missing context. Use `search_knowledge` for follow-up queries and `fetch_document` to read full chunks. Produce a critique with specific requests for clarification."
- **Agent C (Synthesizer):** "You produce the final answer. Synthesize Agent A's research and Agent B's critique into a concise, cited answer. Structure: summary, key findings with citations, confidence assessment."

An ADK `SequentialAgent` orchestrates the flow: Researcher → Critic → Synthesizer. Each agent receives the previous agent's output in its context.

Agent thinking and intermediate results are streamed via ADK's built-in event system, which the AG-UI middleware converts to SSE events (`RUN_STARTED` → `TEXT_MESSAGE_START` → `TEXT_MESSAGE_CONTENT`* → `TEXT_MESSAGE_END` → `RUN_FINISHED`).

**7. SolidJS Frontend (`frontend/`)**

A Vite + SolidJS SPA with:
- Chat input area (textarea + submit button)
- Streaming output display showing agent labels, tool calls, and reasoning in real-time
- Final answer with citation blocks
- Agent status indicators (thinking / searching / synthesizing / done)
- Conversation sidebar (left panel): lists all conversations by auto-generated title, newest first. Current conversation highlighted. Delete button per conversation. New conversation button at top.
- Conversation persistence via localStorage (no backend storage). Data model: `{ id, title, createdAt, messages[] }`. Title auto-generated from first user message (~50 chars, word-bounded). LM Studio UI is the reference.
- Tailwind CSS for styling (no component library dependency)

Connects to `POST /api/chat` via `@tanstack/ai-solid`'s `useChat` hook with `fetchServerSentEvents` adapter (AG-UI protocol over SSE).

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

The knowledge base combines the **MCP specification** and the **Google ADK documentation**, pulled as markdown/text, chunked (~500-token chunks, 50-token overlap), embedded, and upserted into pgvector via a one-time seeding script (`scripts/seed_knowledge_base.py`).

**MCP Sources (official spec repo — already cloned locally):**

| Source | Path | Content |
|---|---|---|
| Getting Started | `docs/docs/getting-started/intro.mdx` | What MCP is, why it exists |
| Architecture | `docs/docs/learn/architecture.mdx` | Host/client/server model, transports overview |
| Server Concepts | `docs/docs/learn/server-concepts.mdx` | Tools, resources, prompts, capabilities |
| Client Concepts | `docs/docs/learn/client-concepts.mdx` | Client lifecycle, roots, sampling |
| Build Server | `docs/docs/develop/build-server.mdx` | MCP server implementation with SDK |
| Build Client | `docs/docs/develop/build-client.mdx` | MCP client implementation with SDK |
| Connect Local | `docs/docs/develop/connect-local-servers.mdx` | Running MCP servers locally |
| Connect Remote | `docs/docs/develop/connect-remote-servers.mdx` | Remote MCP, auth, streaming HTTP |
| Spec — Tools | `docs/specification/2025-11-25/server/tools.mdx` | Tool definition schema |
| Spec — Resources | `docs/specification/2025-11-25/server/resources.mdx` | Resource definition schema |
| Spec — Prompts | `docs/specification/2025-11-25/server/prompts.mdx` | Prompt template schema |
| Spec — Transports | `docs/specification/2025-11-25/basic/transports.mdx` | Stdio vs Streamable HTTP transports |
| Spec — Authorization | `docs/specification/2025-11-25/basic/authorization.mdx` | OAuth, auth flows |
| Spec — Lifecycle | `docs/specification/2025-11-25/basic/lifecycle.mdx` | Initialization, capability negotiation |
| Spec — Schema | `docs/specification/2025-11-25/schema.mdx` | JSON-RPC protocol schema |
| Blog — MCP Extensions | `blog/content/posts/2026-03-11-understanding-mcp-extensions.md` | Extension mechanism explainer |
| Blog — Transport Future | `blog/content/posts/2025-12-19-mcp-transport-future.md` | SSE polling, Streamable HTTP evolution |
| Blog — Tool Annotations | `blog/content/posts/2026-03-16-tool-annotations.md` | Tool annotation spec (readAfterWrite, destructiveHint, etc.) |
| Blog — Roadmap | `blog/content/posts/2026-03-09-roadmap-update.md` | MCP 2026 roadmap, near-term priorities |
| Blog — Agentic AI Foundation | `blog/content/posts/2025-12-09-mcp-joins-agentic-ai-foundation.md` | MCP governance and foundation |

**ADK Sources (official docs at adk.dev):**

| Source | URL | Content |
|---|---|---|
| About ADK | `adk.dev/get-started/about/` | Core concepts: Agent, Tool, Callbacks, Session, State, Memory, Artifact, Runner, Events |
| Agents | `adk.dev/agents/` | LlmAgent, workflow agents (Sequential/Parallel/Loop), multi-agent design |
| Agent Config | `adk.dev/agents/config/` | YAML-based agent definitions without code |
| Tools | `adk.dev/tools/` | FunctionTool, AgentTool, code execution, MCP Toolset |
| MCP Tools | `adk.dev/tools-custom/mcp-tools/` | **ADK as MCP client + ADK as MCP server** — critical for the demo |
| Models | `adk.dev/agents/models/` | Gemini, other LLMs via BaseLlm interface, model routing |
| Context | `adk.dev/context/` | Context object, session state, artifact management |
| Memory | `adk.dev/memory/` | Long-term memory across sessions |
| Skills | `adk.dev/skills/` | Self-contained skill units for agents |
| Graph Workflows | `adk.dev/graphs/` | ADK 2.0 graph-based orchestration |
| Tutorial — Agent Team | `adk.dev/tutorials/agent-team/` | Multi-agent team tutorial with real code |
| API Reference (Python) | `adk.dev/api-reference/python/` | Full Python SDK reference |
| Integrations | `adk.dev/integrations/` | Ecosystem integrations (data connectors, third-party) |

**Total: ~33 documents.** This is comprehensive enough that a user can ask detailed questions about MCP server design, ADK agent patterns, tool integration, transport selection, or auth flows and get grounded answers.

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

## Out of Scope

- Production user authentication (the demo is open-access; auth can be added later per client requirements). Token abuse prevention is handled via rate-limiting (see Further Notes).
- Multi-tenancy or per-user RAG indexes
- Fine-tuning any LLM
- Pinecone or any non-pgvector vector store
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

2. **Proposal leverage:** The live demo URL is the centerpiece of every proposal. The pitch: *"I built exactly this — a multi-agent RAG system where three specialist agents collaborate via MCP, search a pgvector knowledge base, and produce cited answers streamed to a live dashboard. Here's a link. Try asking it anything about MCP server design."*

### Token Abuse Prevention

The demo is public and unauthenticated. Without protection, a malicious actor could exhaust the DeepSeek API budget through repeated requests. Mitigations:

1. **IP-based rate limiting** via Caddy (or Nginx) at the reverse proxy layer: max 10 requests per IP per minute, burst up to 20. This is configured in the Caddyfile / Nginx config, not in application code.
2. **Daily token budget** enforced at the FastAPI middleware layer: a hard cap on total LLM tokens consumed per day. When the budget is exhausted, all subsequent requests return `429 Too Many Requests` with a message like "Daily demo budget reached. Try again tomorrow." The budget is stored in a simple file on the VPS (no database needed).
3. **Query length limit** enforced by Pydantic: max 500 characters per question. Longer inputs are rejected at the API boundary.

These are demo-grade mitigations — sufficient to deter casual abuse without the complexity of real authentication. If a client wants production security, they pay for it.

The market-validated posting that this demo directly addresses:

> "Create AI agents (3 to 4) and an MCP server with Tools registered. 3 agents using Google and 1 agent using Crew.AI. Need to prove how these agents can communicate via MCP server. Use a small public dataset and build a search to lookup in local dataset and then send to LLM via API call."

Substitute Google ADK for Crew.AI and the spec is identical.
