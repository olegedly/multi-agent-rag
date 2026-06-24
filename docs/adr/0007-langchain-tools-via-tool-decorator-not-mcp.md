# ADR-0007: LangChain Agents Call RAG via Native @tool, Not Through MCP

The LangChain agent pipeline accesses the RAG store through **native LangChain `@tool` functions** that call `backend/rag/search.py` directly — not through the MCP server. The `corpus_id` is baked into a closure at per-request tool construction time, making it physically inaccessible to the LLM.

The MCP server continues to exist as a **standalone external service** for pi development, MCP Inspector, Claude Desktop, and as a reference implementation of the RAG tool contract. It shares the same query functions from `backend/rag/search.py`.

**Status:** accepted, supersedes ADR-0007 (draft)

**Considered options:**
- *Embedded MCP subprocess + ADK ``MCPToolset``:* rejected — the project migrated from ADK to LangChain `create_agent()`. LangChain's native `@tool` decorator provides the same closure-scoping pattern without the MCP protocol overhead.
- *Session-state-instructed corpus_id:* rejected for production — leaves `corpus_id` as an LLM-controllable parameter, risking silent cross-corpus contamination.
- *Wrapped ``ScopedMcpTool`` subclassing LangChain internals:* rejected — fragile against version bumps, still advertises `corpus_id` in the tool schema.

**Consequences:**
- `backend/rag/search.py` is the single source of truth for RAG logic. Both the MCP server and LangChain tool factory import and call the same functions here.
- The MCP server uses `mcp_server/server.py` — standalone, SSE-capable, independently runnable. No change to `dev.sh` or `.mcp.json`.
- LangChain tool construction happens per-request via `create_rag_tools(corpus_id=...)` factory, receiving the active `corpus_id` from the request context.
- Adding a new RAG feature (hybrid search, reranking) means modifying the query layer once — both consumers (LangChain, MCP) pick it up without changes.
- The production Docker image does not include the MCP server process or its entry points.
