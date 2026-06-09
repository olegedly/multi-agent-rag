# ADR-0004: Demo Abuse Prevention with Middleware Stack

Three-layer defense: Caddy IP rate limiting (10 req/min per IP), daily token budget (ASGI middleware, file-backed), and query validation (FastAPI middleware). The budget is disabled in dev via `DEMO_DISABLE_BUDGET=true` since `/data/demo-budget.json` doesn't exist natively.

Token accounting fires from `usage_callback` on the `LLMClient` — the same seam used by the ADK adapter's usage callback — rather than from a separate interceptor.

**Status:** accepted

**Consequences:**
- Single `ChatGuard` middleware combines budget + validation (reads body once)
- Budget is file-based, not DB-based — sufficient for a single-worker demo
- Query length cap at 500 chars rendered in the Pydantic schema
