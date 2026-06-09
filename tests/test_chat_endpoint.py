"""Tests for the LangChain chat SSE streaming endpoint.

Exercises ``POST /api/chat/{slug}`` via ``TestClient`` with a stubbed
agent pipeline.
"""

from __future__ import annotations

import json
from typing import AsyncIterable
from unittest.mock import ANY

import pytest
from fastapi.testclient import TestClient

from backend.corpus_config import CorporaConfig


# ── Fake agent pipeline ──────────────────────────────────────────────────────


async def _fake_pipeline(
    messages: list[dict],
    corpus_slug: str,
    **kwargs,
) -> AsyncIterable[dict]:
    """A deterministic fake pipeline for testing the SSE endpoint shape."""
    # 1. Content event
    yield {"type": "content", "delta": "Hello", "content": "Hello", "role": "assistant"}
    # 2. Tool call event
    yield {
        "type": "tool_call",
        "toolCall": {
            "id": "call_1",
            "type": "function",
            "function": {"name": "rag_search", "arguments": '{"query":"test"}', "output": "..."},
        },
    }
    # 3. Another content event
    yield {"type": "content", "delta": " World", "content": "Hello World", "role": "assistant"}
    # 4. Done event
    yield {"type": "done", "finishReason": "stop", "usage": {"promptTokens": 10, "completionTokens": 5}}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def corpora_config():
    """Two corpora for route testing."""
    return CorporaConfig.from_dicts([
        {"id": "corpus-a-uuid", "slug": "eu-ai-act", "name": "EU AI Act",
         "description": "Test corpus", "chunker": "markdown-heading",
         "documents": "corpora/eu-ai-act/**/*.md"},
        {"id": "corpus-b-uuid", "slug": "mcp-spec", "name": "MCP Spec",
         "description": "Test corpus", "chunker": "markdown-heading",
         "documents": "corpora/mcp-spec/**/*.md"},
    ])


@pytest.fixture
def app(corpora_config, monkeypatch):
    """Build the FastAPI app with fake pipeline injected."""
    from backend.config import Settings
    from backend.main import create_app

    settings = Settings(demo_disable_budget=True)  # no /data/ needed
    app = create_app(settings=settings, corpora_config=corpora_config)

    # Override the pipeline dependency
    monkeypatch.setattr("backend.main.run_pipeline", _fake_pipeline)

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ── Tracer bullet 3: SSE streaming endpoint shape ───────────────────────────


class TestChatEndpoint:
    """POST /api/chat/{slug} returns TanStack SSE events."""

    def test_returns_sse_content_type(self, client):
        response = client.post(
            "/api/chat/eu-ai-act",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

    def test_unknown_slug_returns_404(self, client):
        response = client.post(
            "/api/chat/nonexistent",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert response.status_code == 404

    def test_sse_events_are_parseable(self, client):
        """Each SSE data line should be valid JSON."""
        response = client.post(
            "/api/chat/eu-ai-act",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        for line in response.text.strip().split("\n"):
            if line.startswith("data: ") and line[6:] != "[DONE]":
                data = json.loads(line[6:])
                assert "type" in data

    def test_sse_contains_content_and_done_events(self, client):
        """The stream should contain content deltas and a done event."""
        response = client.post(
            "/api/chat/eu-ai-act",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        events = []
        for line in response.text.strip().split("\n"):
            if line.startswith("data: ") and line[6:] != "[DONE]":
                events.append(json.loads(line[6:]))

        types = [e["type"] for e in events]
        assert "content" in types
        assert "done" in types
        assert events[-1]["type"] == "done"

    def test_sse_ends_with_done_marker(self, client):
        """Final line should be the [DONE] sentinel."""
        response = client.post(
            "/api/chat/eu-ai-act",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        lines = response.text.strip().split("\n")
        assert lines[-1].strip() == "data: [DONE]"
    # ── ChatGuard middleware still active ──────────────────────────────────

    def test_middleware_still_blocks_long_messages(self, client):
        """ChatGuard should still validate query length on the new endpoint."""
        response = client.post(
            "/api/chat/eu-ai-act",
            json={"messages": [
                {"role": "user", "content": "x" * 600},
            ]},
        )
        assert response.status_code == 422

    def test_corpora_endpoint_still_works(self, client):
        response = client.get("/api/corpora")
        assert response.status_code == 200
        slugs = [c["slug"] for c in response.json()]
        assert "eu-ai-act" in slugs
