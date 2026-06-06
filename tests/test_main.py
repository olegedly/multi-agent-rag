"""Tests for the FastAPI application entry point.

Patches the LLM factory at module load time so the app uses a
FakeLLMClient for all routes.
"""

import json

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeLLMClient


# ---------------------------------------------------------------------------
# Patch the factory before ``backend.main`` is imported so the module-level
# ``get_llm_client()`` call returns a FakeLLMClient.
# ---------------------------------------------------------------------------

import backend.llm.factory as _factory_mod

_original_factory = _factory_mod.create_llm_client
_factory_mod.create_llm_client = lambda: FakeLLMClient()

import importlib
import backend.main as _main_mod

importlib.reload(_main_mod)

from backend.main import app


@pytest.fixture(scope="module", autouse=True)
def _restore_factory():
    yield
    _factory_mod.create_llm_client = _original_factory


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ── Tests ────────────────────────────────────────────────────────────────────


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
