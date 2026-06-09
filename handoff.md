# Handoff: RAG Tool Calling — State Plumbing Broken (corpusId Not Reaching tool_context)

## Context

See prior handoff at `/tmp/handoff-rag-tool-calling.md` for the serialization fix that made tool calls actually execute. That fix works. This session diagnosed the next bug.

## The Problem

**Tool calls execute, but every call returns `"No active corpus"`** because `corpusId` never appears in `tool_context.state` inside `backend/agents/tools.py`.

### Evidence (from Chrome SSE stream)

- 14+ `rag_search` calls — all return `{"results": [], "error": "No active corpus — start a conversation from a knowledge base route"}`
- 4+ `rag_read_document` calls with hallucinated chunk IDs (592-601) — same error
- Final `STATE_SNAPSHOT` at `RUN_FINISHED` shows only: `{_ag_ui_thread_id, _ag_ui_app_name, _ag_ui_user_id}` — **no `corpusId`**
- The model spirals for ~3 minutes, trying increasingly creative queries, all fail identically

### Frontend sends corpusId

`frontend/src/conversations/useChatStore.ts` line 18:
```ts
body: {
  state: { corpusId: "315e41aa-8657-46c0-ac4b-ea4355babf0a" },
},
```

## What Was Investigated

### State pipeline traced in `ag_ui_adk` (installed package)

The pipeline in `adk_agent.py` looks correct at every layer:

1. **Line 2190** — `state_with_context = dict(input.state)` — reads `input.state` from `POST /api/chat` body
2. **Line 2194** — Strips `_INTERNAL_STATE_KEYS` (which does NOT include `corpusId`)
3. **Line 2210** — `persistent_state` gets non-temp keys (should include `corpusId`)
4. **Line 2219** — `persistent_state` passed to `_ensure_session_exists(..., initial_state=persistent_state)`
5. **Line 2234** — `update_session_state(backend_session_id, app_name, user_id, persistent_state)` updates session state
6. **`_ensure_session_exists`** → `session_manager.get_or_create_session(... initial_state=initial_state)` → `session_service.create_session(... state=state)` — state merged into ADK session

### ADK `tool_context.state`

The tool reads via `tool_context.state.get("corpusId")` — confirmed in `backend/agents/tools.py`. Diagnostic logging was added (`log.warning` at import time).

### What was NOT yet checked

- **Whether the POST body actually includes `corpusId`** — Chrome's network tab shows response bodies but NOT request bodies. Need to either:
  - Add backend middleware to log the raw request body
  - Or use `chrome_evaluate` to intercept `fetch` on the client side before the next request
- **What TanStack AI Solid's `useChat` actually sends** — the `body` config option in `useChatStore.ts` may not map 1:1 to the POST body. Need to verify TanStack's wire format.

## Next Steps (in order)

1. **Verify request body** — Add a FastAPI middleware that logs `await request.body()` on POST /api/chat to confirm `corpusId` is in the wire payload
2. **If corpusId IS in the body** → debug ADK state merge (add logging to `_ensure_session_exists`, `update_session_state`, and check ADK session state after create)
3. **If corpusId is NOT in the body** → debug TanStack AI Solid's body serialization (what `body: { state: {...} }` actually produces)
4. **Fallback approach** — If the ADK pipeline truly can't propagate state to tool_context, hardcode the corpusId in the agent instruction or tool function as a temporary workaround

## Files Modified This Session

- `backend/agents/tools.py` — Added diagnostic logging to `rag_search`:
  - `import logging; log = logging.getLogger(__name__)` at top
  - Logs `tool_context.state` and `corpus_id` before the guard clause

## Environment

- Frontend: Vite on port 3000 (Chrome tab)
- Backend: uvicorn on port 8000 (`fastapi dev` with hot reload)
- LLM: `z-ai/glm-4.5-air:free` via OpenRouter
- Config: `PROVIDER=openai`, `BASE_URL=https://openrouter.ai/api/v1`
- DB: Postgres on localhost:5432, 1326 docs in corpus `315e41aa-...`
- All services managed by `dev.sh`
