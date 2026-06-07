"""Tests for the FastAPI application factory.

Uses ``create_app()`` with an injected ``FakeLLMClient`` — no import-time
patching or ``importlib.reload`` needed.
"""

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from tests.fakes import FakeLLMClient


SAMPLE_CORPORA = [
    {
        "id": "a1b2c3d4-1234-5678-9abc-def012345678",
        "slug": "mcp-spec",
        "name": "MCP Specification",
        "description": "MCP spec and ADK documentation",
    },
    {
        "id": "b2c3d4e5-2345-6789-abcd-ef0123456789",
        "slug": "eu-ai-act",
        "name": "EU AI Act",
        "description": "European Union AI regulation",
    },
]


# ── Fixture ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path):
    app = create_app(
        llm_client=FakeLLMClient(),
        settings=Settings(
            demo_budget_file=str(tmp_path / "budget.json"),
        ),
        corpora=SAMPLE_CORPORA,
    )
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


# ── Corpora endpoint ────────────────────────────────────────────────────────


class TestCorporaEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/corpora")
        assert response.status_code == 200

    def test_returns_corpus_list(self, client: TestClient) -> None:
        response = client.get("/api/corpora")
        data = response.json()
        assert len(data) == 2
        assert data[0]["slug"] == "mcp-spec"
        assert data[1]["slug"] == "eu-ai-act"

    def test_each_corpus_has_required_fields(self, client: TestClient) -> None:
        response = client.get("/api/corpora")
        data = response.json()
        for entry in data:
            assert "id" in entry
            assert "slug" in entry
            assert "name" in entry
            assert "description" in entry

    def test_empty_when_no_corpora_configured(self, tmp_path) -> None:
        app = create_app(
            llm_client=FakeLLMClient(),
            settings=Settings(
                demo_budget_file=str(tmp_path / "budget.json"),
            ),
            corpora=[],
        )
        with TestClient(app) as c:
            response = c.get("/api/corpora")
            assert response.json() == []


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
