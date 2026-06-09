# ADR-0001: LLM Client Abstraction with Abstract Base Class

The LLM layer is abstracted behind an `LLMClient` ABC with two concrete adapters (`OpenAIClient`, `AnthropicClient`) and a config-driven factory. This keeps provider switching a config change (`LLM_PROVIDER` env var) rather than a code change, and allows tests to inject `FakeLLMClient` at the same seam production code uses.

The `generate_stream` API was designed as a coroutine returning `AsyncIterable[tuple[str, Usage | None]]` — usage data flows through the return channel rather than through mutable instance state (`last_usage`), keeping the abstract seam pure.

**Status:** accepted

**Considered options:**
- Protocol class: discarded because the `usage_callback` attribute + abstract methods made ABC cleaner
- No abstraction (direct SDK calls): discarded — would make testing and provider switching expensive

**Consequences:**
- ADK integration requires `AdkLlmAdapter(BaseLlm)` bridge
- Each concrete client owns an `HttpTransport` instance for HTTP; tests substitute `FakeTransport`
