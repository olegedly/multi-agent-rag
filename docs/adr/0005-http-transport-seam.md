# ADR-0005: HTTP Transport as a Replaceable Seam

HTTP is abstracted behind a `Transport` Protocol class. `HttpTransport` owns an `httpx.AsyncClient`; `FakeTransport` is injected in tests. Both `OpenAIClient` and `AnthropicClient` accept an optional `transport` parameter, defaulting to a fresh `HttpTransport`.

This keeps `pytest-httpx` usage confined to the transport module's own tests. All other tests use `FakeTransport` or `FakeLLMClient`.

**Status:** accepted

**Consequences:**
- `_parse_error_body` lives in `transport.py` as a shared utility (hoisted from duplicated implementations)
- Transport instances are collected during `create_app()` and closed in the lifespan handler
