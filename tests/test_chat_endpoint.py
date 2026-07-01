"""Tests for the LangChain chat SSE streaming endpoint.

Exercises ``POST /api/chat/{slug}`` via ``TestClient`` with a stubbed
agent pipeline.
"""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from backend.corpus_config import CorporaConfig

from ag_ui.core.events import (
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)


# ── Fake agent pipeline ──────────────────────────────────────────────────────


async def _fake_pipeline(
    messages: list[dict],
    corpus_slug: str,
    **kwargs,
):
    """A deterministic fake pipeline for testing the SSE endpoint shape."""
    ts = 1000000
    yield RunStartedEvent(thread_id="test-thread", run_id="test-run", timestamp=ts)
    yield TextMessageStartEvent(message_id="msg-1", role="assistant", timestamp=ts)
    yield TextMessageContentEvent(message_id="msg-1", delta="Hello", timestamp=ts)
    yield TextMessageEndEvent(message_id="msg-1", timestamp=ts)
    yield RunFinishedEvent(
        thread_id="test-thread",
        run_id="test-run",
        timestamp=ts,
        finishReason="stop",  # type: ignore[call-arg]
        usage={"promptTokens": 10, "completionTokens": 5},  # type: ignore[call-arg]
    )


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
    monkeypatch.setattr("backend.main.run_orchestrator", _fake_pipeline)

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
        """Each SSE data line should be valid JSON with an AG-UI event type."""
        response = client.post(
            "/api/chat/eu-ai-act",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        for line in response.text.strip().split("\n"):
            if line.startswith("data: "):
                data = json.loads(line[6:])
                assert "type" in data

    def test_sse_contains_ag_ui_event_types(self, client):
        """The stream should contain AG-UI event types."""
        response = client.post(
            "/api/chat/eu-ai-act",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        events = []
        for line in response.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        types = [e["type"] for e in events]
        assert "RUN_STARTED" in types
        assert "TEXT_MESSAGE_START" in types
        assert "TEXT_MESSAGE_CONTENT" in types
        assert "TEXT_MESSAGE_END" in types
        assert "RUN_FINISHED" in types
        assert events[-1]["type"] == "RUN_FINISHED"

    def test_sse_event_sequence(self, client):
        """Events should appear in correct AG-UI order."""
        response = client.post(
            "/api/chat/eu-ai-act",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        events = []
        for line in response.text.strip().split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        types = [e["type"] for e in events]
        assert types == [
            "RUN_STARTED",
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_END",
            "RUN_FINISHED",
        ]
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
