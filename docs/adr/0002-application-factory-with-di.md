# ADR-0002: Application Factory with Dependency Injection

`create_app()` accepts optional `llm_client`, `settings`, and `corpora_config` parameters. When omitted they are created from environment config. The module-level `app` is lazily initialised via `__getattr__` so that importing `backend.main` on CI doesn't crash from missing `.env`.

This eliminates `importlib.reload` trickery and allows tests to call `create_app(llm_client=FakeLLMClient())` directly with no module reassignment.

**Status:** accepted

**Consequences:**
- The lifespan handler closes `HttpTransport` connections on shutdown
- `fastapi dev` compatibility is preserved via the lazy `__getattr__("app")` pattern
