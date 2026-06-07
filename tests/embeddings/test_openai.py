"""Tests for the OpenRouter embedding client.

Mirrors the LLM client test pattern: uses ``FakeTransport`` to avoid
real HTTP calls, asserts request body shape and response parsing.
"""

import json

import pytest

from backend.embeddings.openai import OpenRouterEmbeddingClient
from tests.fakes import FakeTransport


class TestOpenRouterEmbeddingClient:
    """OpenRouterEmbeddingClient uses OpenAI-compatible ``/v1/embeddings``."""

    async def test_request_body_shape(self) -> None:
        """POST body matches OpenAI embedding format."""
        transport = FakeTransport.with_body(
            json.dumps({
                "data": [
                    {"embedding": [0.1] * 768, "index": 0},
                    {"embedding": [0.2] * 768, "index": 1},
                ],
                "model": "qwen/qwen3-embedding-768",
                "usage": {"prompt_tokens": 10, "total_tokens": 10},
            }).encode()
        )
        client = OpenRouterEmbeddingClient(
            model="qwen/qwen3-embedding-768",
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
            dimensions=768,
            transport=transport,
        )

        result = await client.embed_texts(["hello world", "second text"])

        # Request body
        assert len(transport.sent_requests) == 1
        _url, headers, body = transport.sent_requests[0]
        assert body["model"] == "qwen/qwen3-embedding-768"
        assert body["input"] == ["hello world", "second text"]
        assert body["dimensions"] == 768
        assert headers["Authorization"] == "Bearer sk-test"

        # Response
        assert len(result) == 2
        assert len(result[0]) == 768
        assert len(result[1]) == 768

    async def test_single_text(self) -> None:
        """A single text returns one embedding vector."""
        transport = FakeTransport.with_body(
            json.dumps({
                "data": [{"embedding": [0.5] * 768, "index": 0}],
                "model": "test-model",
                "usage": {"prompt_tokens": 3, "total_tokens": 3},
            }).encode()
        )
        client = OpenRouterEmbeddingClient(
            model="test-model",
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            dimensions=768,
            transport=transport,
        )

        result = await client.embed_texts(["single"])

        assert len(result) == 1
        assert len(result[0]) == 768

    async def test_api_error_raises_embedding_error(self) -> None:
        """4xx response raises ``EmbeddingError`` with status and message."""
        transport = FakeTransport.with_error(
            status=401,
            body=json.dumps({"error": {"message": "Invalid API key"}}).encode(),
        )
        client = OpenRouterEmbeddingClient(
            model="test-model",
            api_key="sk-bad",
            base_url="https://api.example.com/v1",
            dimensions=768,
            transport=transport,
        )

        from backend.embeddings.protocol import EmbeddingError

        with pytest.raises(EmbeddingError) as exc:
            await client.embed_texts(["fail"])

        assert exc.value.status == 401

    async def test_empty_text_list(self) -> None:
        """Empty list is passed through (API decides response)."""
        transport = FakeTransport.with_body(
            json.dumps({"data": [], "model": "test", "usage": {"prompt_tokens": 0, "total_tokens": 0}}).encode()
        )
        client = OpenRouterEmbeddingClient(
            model="test-model",
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            dimensions=768,
            transport=transport,
        )

        result = await client.embed_texts([])
        assert result == []
