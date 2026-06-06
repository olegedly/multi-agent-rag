"""Tests for the FastAPI application factory.

Uses ``create_app()`` with an injected ``FakeLLMClient`` — no import-time
patching or ``importlib.reload`` needed.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.fakes import FakeLLMClient


# ── Fixture ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    app = create_app(llm_client=FakeLLMClient())
    with TestClient(app) as c:
        yield c


# ── Health ───────────────────────────────────────────────────────────────────


class TestHealth:
    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_returns_json(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.headers["content-type"] == "application/json"

    def test_contains_app_name(self, client: TestClient) -> None:
        response = client.get("/api/health")
        data = response.json()
        assert data["app"] == "multi-agent-rag"
        assert data["status"] == "ok"


# ── Chat endpoint ────────────────────────────────────────────────────────────


class TestChatEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        """POST /api/chat returns 200 and streams AG-UI SSE events."""
        from ag_ui.core.types import UserMessage

        msg = UserMessage(id="msg-1", content="hello")
        response = client.post(
            "/api/chat",
            json={
                "thread_id": "test-thread",
                "run_id": "test-run",
                "state": {},
                "messages": [msg.model_dump(mode="json")],
                "tools": [],
                "context": [],
                "forwarded_props": {},
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "RUN_STARTED" in response.text
        assert "RUN_FINISHED" in response.text
