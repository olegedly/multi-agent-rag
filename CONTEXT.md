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
A standalone stdio-process exposing two corpus-scoped tools (`search_corpus`, `read_document`). Runs independently of the FastAPI app. Agents connect via ADK `MCPToolset`.
_Avoid_: Tool server, plugin, skill server

**RAG Search**:
Semantic vector search over a single corpus using pgvector cosine similarity (`<=>` operator). Returns typed `SearchResult` objects with content, metadata, and similarity score.

**Chunker**:
A per-corpus document-splitting strategy configured in `corpora.yaml`. Strategies: `markdown-heading` (headings → ~500-token chunks), `paragraph` (double-newline), `recursive` (character-based fallback), `fixed-size` (token-count with overlap).
