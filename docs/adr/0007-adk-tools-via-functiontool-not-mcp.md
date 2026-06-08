# ADR-0007: ADK Agents Call RAG via Native FunctionTool, Not Through MCP

The production ADK multi-agent pipeline (Researcher → Critic → Synthesizer) accesses the RAG store through **native ADK `FunctionTool`s** that call `backend/rag/search.py` directly — not through the MCP server. The `corpus_id` is baked into a closure at per-request tool construction time, making it physically inaccessible to the LLM.

The MCP server continues to exist as a **standalone external service** for pi development, MCP Inspector, Claude Desktop, and as a reference implementation of the RAG tool contract. It shares the same query functions from `backend/rag/search.py`.

**Status:** accepted, supersedes ADR-0007 (draft)

**Considered options:**
- *Embedded MCP subprocess + ADK `MCPToolset`:* rejected — adds latency, subprocess lifecycle complexity, JSON serialization overhead. ADK's own agents don't benefit from the MCP protocol layer.
- *Session-state-instructed corpus_id (Option A):* rejected for production — leaves `corpus_id` as an LLM-controllable parameter, risking silent cross-corpus contamination. Kept as a fallback if per-request tool construction proves infeasible.
- *Wrapped `ScopedMcpTool` subclassing ADK internals:* rejected — fragile against ADK minor version bumps (underscored APIs), still advertises `corpus_id` in the tool schema.

**Consequences:**
- `backend/rag/search.py` is the single source of truth for RAG logic. Both the MCP server and ADK tool wrappers import and call the same functions here.
- The MCP server uses `create_mcp_server()` from `backend/mcp_server/server.py` — standalone, SSE-capable, independently runnable. No change to `dev.sh` or `.mcp.json`.
- ADK tool construction happens per-request via a factory, receiving the active `corpus_id` from the request context (extracted from AG-UI session input).
- Adding a new RAG feature (hybrid search, reranking) means modifying the query layer once — both consumers (MCP, ADK) pick it up without changes.
- The production Docker image does not include the MCP server process or its entry points.
- Documented in CONTEXT.md under "RAG Query Layer", "Corpus-scoped ADK Tool", and the revised "MCP Server" entry.
