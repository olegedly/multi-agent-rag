# Multi-Agent RAG

A config-driven multi-agent research system with pgvector RAG, MCP tool servers, and Google ADK orchestration. Answers are grounded in curated knowledge bases, each scoped to a single corpus.

## Language

**Corpus**:
A curated, independently-ingestible collection of documents on a single domain (e.g. "EU AI Act"). Has a persistent UUIDv4 (`corpus_id`), a human-readable URL `slug`, and a display `name`. Every chunk in the vector store is tagged with its `corpus_id`; retrieval always filters by it.
_Avoid_: Knowledge base, dataset, library

**Corpus slug**:
The URL segment used in `/corpora/<slug>` routes. Human-readable, mutable. Renaming breaks bookmarks (handled gracefully by the frontend).
_Avoid_: Route, path, identifier

**MCP Server**:
A standalone stdio-process exposing two corpus-scoped tools (`search_corpus`, `read_document`). Runs independently of the FastAPI app. Serves external MCP-native clients (pi, MCP Inspector, Claude Desktop) and acts as a sharable reference implementation of the RAG tool contract. The production ADK pipeline does **not** route through it — agents call the RAG functions directly via native tools.
_Avoid_: The only path to RAG (it isn't), the production tool layer (ADK bypasses it)

**RAG Search**:
Semantic vector search over a single corpus using pgvector cosine similarity (`<=>` operator). Returns typed `SearchResult` objects with content, metadata, and similarity score.

**RAG Query Layer (`backend/rag/search.py`)**:
Single source of truth for RAG queries. Both the MCP server and the ADK agent tools import and call the same `search_corpus` / `read_document` functions here. New retrieval features (hybrid search, reranking) are added here once — both consumers pick them up for free.
_Avoid_: Duplicating logic across paths

**Corpus-scoped ADK Tool**:
A native ADK `FunctionTool` (not an MCP tool) that wraps a RAG query function with the active `corpus_id` baked into a closure. The agent sees parameters the LLM should control (query, top_k) — the `corpus_id` is physically inaccessible, preventing contamination.
_Avoid_: Exposing `corpus_id` as an LLM-controllable parameter

**Chunker**:
A per-corpus document-splitting strategy configured in `corpora.yaml`. Strategies: `markdown-heading` (headings → ~500-token chunks), `paragraph` (double-newline), `recursive` (character-based fallback), `fixed-size` (token-count with overlap).
