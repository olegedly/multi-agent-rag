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

A deployed, interactive multi-agent research system where:

- A user submits a research question via a web dashboard
- Three specialist AI agents (Researcher, Critic, Synthesizer) collaborate via MCP to answer it
- Agents search a pgvector knowledge base (RAG over the MCP specification + ADK documentation)
- The entire reasoning process streams to the dashboard in real-time — tool calls, intermediate findings, final synthesis
- The system is Dockerized and deployed to a VPS with Caddy serving the SolidJS SPA and reverse-proxying to FastAPI

The demo is **self-referential**: it uses ADK + MCP to answer questions about ADK + MCP. This signals deep domain competence to potential clients.

## User Stories

1. As a visitor to the demo, I want to type a natural-language research question into a web dashboard, so that I can see how the system handles my query.
2. As a visitor, I want to see each agent's reasoning and tool calls streamed in real-time, so that I understand the multi-agent collaboration process.
3. As a visitor, I want the final answer to include citations from the knowledge base, so that I trust the output is grounded and not hallucinated.
4. As a potential client, I want to query the system about MCP or ADK topics, so that I can assess the depth of relevant domain knowledge.
5. As a potential client, I want to see the system deployed at a live URL, so that I can evaluate it without running any code.
6. As a potential client, I want to see clean, production-quality code in a public repository, so that I can evaluate engineering practices.
7. As the developer, I want the LLM client to be abstracted behind a single interface that DeepSeek (via its Anthropic-compatible endpoint) satisfies, so that I can explain to future clients that adapting to their preferred provider is a configuration change, not a rewrite.
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
SolidJS SPA ──SSE──▶ FastAPI ──▶ Google ADK Orchestrator
                              │         ├── Agent A (Researcher)
                              │         ├── Agent B (Critic)
                              │         └── Agent C (Synthesizer)
                              │
                              ├── MCP Server (search_knowledge, fetch_document)
                              │         └── pgvector RAG
                              │               └── PostgreSQL (Supabase Cloud)
                              │
                              └── DeepSeek LLM (via Anthropic-compatible endpoint)
```

### Modules

**1. LLM Client Abstraction (`llm/client.py`)**

A thin wrapper around the Anthropic SDK, configured to call DeepSeek's Anthropic-compatible endpoint (`https://api.deepseek.com/anthropic`). The tool-use loop (call → tool_use → execute → submit → call again) lives here.

The interface is designed to be provider-agnostic: `base_url` and `api_key` are environment variables. For the demo they point at DeepSeek. Paying clients who want real Claude would change those two values — but that is their choice and their expense. The demo never calls Anthropic's API.

This is a **deep module**: the rest of the system never knows which LLM is behind the interface.

**2. FastAPI Backend (`api/`)**

Standard FastAPI application with:
- `POST /api/chat` — accepts a question, invokes the ADK orchestrator, returns a streaming SSE response
- Pydantic models for request/response schemas
- Dependency injection for the LLM client, database session, and ADK runtime

**3. RAG Pipeline (`rag/`)**

- Document chunking (recursive text splitter targeting ~500-token chunks with 50-token overlap)
- Embedding via DeepSeek's embedding API (OpenAI-compatible client shape)
- Storage in Supabase PostgreSQL with pgvector `VECTOR(1536)` column
- IVFFlat index on the embedding column for fast cosine similarity search
- Query flow: embed user question → `SELECT ... ORDER BY embedding <=> $query LIMIT 5` → return chunks as context

**4. MCP Server (`mcp_server/`)**

A Python MCP server using the official `mcp` SDK exposing:
- `search_knowledge(query: str, top_k: int = 5)` — semantic search over the RAG index
- `fetch_document(chunk_ids: list[str])` — retrieve full document chunks by ID

Both tools are thin wrappers over the RAG pipeline. The MCP server can run standalone (for testing with MCP Inspector or Claude Desktop) or embedded in the FastAPI process.

**5. Google ADK Agent System (`agents/`)**

Three specialist agents, each defined as an ADK `LlmAgent`:

- **Agent A (Researcher):** "You search the knowledge base for facts, dates, definitions, and specifications relevant to the user's question. Use the `search_knowledge` tool. Report your findings with exact citations."
- **Agent B (Critic):** "You review Agent A's findings. Identify gaps, contradictions, weak citations, or missing context. Use `search_knowledge` for follow-up queries and `fetch_document` to read full chunks. Produce a critique with specific requests for clarification."
- **Agent C (Synthesizer):** "You produce the final answer. Synthesize Agent A's research and Agent B's critique into a concise, cited answer. Structure: summary, key findings with citations, confidence assessment."

An ADK `SequentialAgent` orchestrates the flow: Researcher → Critic → Synthesizer. Each agent receives the previous agent's output in its context.

Agent thinking and intermediate results are streamed via ADK's built-in event system, which feeds into FastAPI's SSE endpoint.

**6. SolidJS Frontend (`frontend/`)**

A Vite + SolidJS SPA with:
- Chat input area (textarea + submit button)
- Streaming output display showing agent labels, tool calls, and reasoning in real-time
- Final answer with citation blocks
- Agent status indicators (thinking / searching / synthesizing / done)
- Conversation sidebar (left panel): lists all conversations by auto-generated title, newest first. Current conversation highlighted. Delete button per conversation. New conversation button at top.
- Conversation persistence via localStorage (no backend storage). Data model: `{ id, title, createdAt, messages[] }`. Title auto-generated from first user message (~50 chars, word-bounded). LM Studio UI is the reference.
- Tailwind CSS for styling (no component library dependency)

Connects to `POST /api/chat` via `EventSource` (SSE).

**7. Deployment (`docker/`)**

Single `docker-compose.yml` with:
- `backend` service (FastAPI + ADK + MCP + RAG, built from `Dockerfile`)
- `postgres` service (PostgreSQL 16 with pgvector pre-installed, for local dev; Supabase handles this in production)
- Nginx or Caddy container serving the SolidJS static build and proxying `/api` to the backend

**8. CI/CD Pipeline (`.github/workflows/`)**

GitHub Actions workflow triggered on pushes to `main` branch:

1. Build the backend Docker image and push to GitHub Container Registry (`ghcr.io`).
2. Build the frontend static assets (`npm run build`) and include them via a multi-stage Dockerfile.
3. Trigger Coolify deployment via its API: send the new image tag and commit SHA, Coolify pulls and redeploys with zero downtime.
4. Coolify handles SSL and reverse proxy on the VPS automatically.

Pipeline: `git push` → GitHub Actions builds + pushes images → Coolify deploys. No manual SSH after initial setup.

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

**The demo exclusively uses DeepSeek** via its Anthropic-compatible endpoint (`https://api.deepseek.com/anthropic`). The Anthropic SDK is used as the client library for its message format, tool-use loop, and streaming support — but it points at DeepSeek's API, never at Anthropic's.

The abstraction layer encodes the *interface* (Anthropic's message/tool/stream shape), not a specific provider. A configuration swap of `base_url` + `api_key` in the environment variables is all that's needed to point at real Claude — but that is only done for paying clients who choose and fund that provider. The demo itself never calls Claude.

Embedding: DeepSeek embedding API via OpenAI-compatible client. Same principle — the interface is provider-agnostic, the demo only calls DeepSeek.

### Observability

ADK's built-in tracing captures each agent's turns, tool calls, token usage, and latency. Traces are viewable through ADK's dev tools. No external observability service (Langfuse, etc.) is added at this stage.

## Testing Decisions

- **What makes a good test:** Test the external behavior of each module through its public interface. Do not test implementation details, LLM output quality, or ADK internals. Mock the LLM client at the network boundary for deterministic tests.
- **MCP server:** Test that `search_knowledge` returns correctly shaped results given a known embedding in the database. End-to-end: seed one chunk, call the tool, assert the chunk appears in results.
- **RAG pipeline:** Test that chunking preserves document boundaries, that embedding + storage round-trips correctly, and that similarity search returns the most relevant chunks first.
- **FastAPI endpoints:** Test that `POST /api/chat` returns a 200 with SSE content-type, that it streams valid JSON events, and that error cases (missing question, empty response) return appropriate error codes.
- **LLM client:** Test that the abstraction layer correctly routes to DeepSeek vs Claude based on the env var, and that tool-use loop retries on transient failures.

Modules with tests: `llm/client.py`, `rag/chunker.py`, `rag/query.py`, `mcp_server/tools.py`, `api/routes.py`.

Prior art: these are standard service-level integration tests — no special patterns needed.

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
