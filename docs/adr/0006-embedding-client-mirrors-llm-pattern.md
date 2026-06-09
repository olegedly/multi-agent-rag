# ADR-0006: Embedding Client Mirrors LLM Pattern

The embedding layer follows the same shape as the LLM layer: an abstract `EmbeddingClient` protocol, a concrete `OpenRouterEmbeddingClient` (OpenAI-compatible `POST /v1/embeddings`), and a config-driven factory. It reuses `HttpTransport` from the LLM layer rather than creating a separate HTTP stack.

`EmbeddingError` mirrors `LLMError` with the same status/message/details structure.

**Status:** accepted

**Consequences:**
- Qwen3 Embedding at 768-dim (MRL) through OpenRouter
- Config vars: `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_DIMENSIONS`
- Swapping embedding providers is a config change, not a code change
