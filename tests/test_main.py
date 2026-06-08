"""Tests for the FastAPI application factory.

Uses ``create_app()`` with an injected ``FakeLLMClient`` — no import-time
patching or ``importlib.reload`` needed.
"""

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.corpus_config import CorporaConfig
from backend.main import create_app
from tests.fakes import FakeLLMClient


SAMPLE_CORPORA = [
    {
        "id": "a1b2c3d4-1234-5678-9abc-def012345678",
        "slug": "mcp-spec",
        "name": "MCP Specification",
        "description": "MCP spec and ADK documentation",
        "chunker": "paragraph",
        "documents": "corpora/mcp-spec/*.md",
    },
    {
        "id": "b2c3d4e5-2345-6789-abcd-ef0123456789",
        "slug": "eu-ai-act",
        "name": "EU AI Act",
        "description": "European Union AI regulation",
        "chunker": "paragraph",
        "documents": "corpora/eu-ai-act/*.md",
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
        corpora_config=CorporaConfig.from_dicts(SAMPLE_CORPORA),
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
            assert "chunker" in entry
            assert "documents" in entry

    def test_empty_when_no_corpora_configured(self, tmp_path) -> None:
        app = create_app(
            llm_client=FakeLLMClient(),
            settings=Settings(
                demo_budget_file=str(tmp_path / "budget.json"),
            ),
            corpora_config=CorporaConfig.from_dicts([]),
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

    def test_with_corpus_id_in_state(self, client: TestClient) -> None:
        """corpusId in state does not break the chat stream."""
        from ag_ui.core.types import UserMessage

        msg = UserMessage(id="msg-1", content="hello")
        response = client.post(
            "/api/chat",
            json={
                "thread_id": "test-thread",
                "run_id": "test-run",
                "state": {"corpusId": "a1b2c3d4-1234-5678-9abc-def012345678"},
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


# ── Agent configuration ──────────────────────────────────────────────────────


class TestAgentTools:
    """The agent is wired with RAG tools via FunctionTool."""

    def test_agent_has_rag_tools(self) -> None:
        """The FunctionTools hide tool_context and expose only
        LLM-controllable parameters."""
        from google.adk.tools.function_tool import FunctionTool
        from backend.agents.tools import make_rag_tools

        rag_search, rag_read_document = make_rag_tools(
            sessionmaker=None, embedding_client=None
        )
        ft1 = FunctionTool(rag_search)
        ft2 = FunctionTool(rag_read_document)
        assert ft1.name == "rag_search"
        assert ft2.name == "rag_read_document"

        # Both tools hide ``tool_context`` from the LLM declaration
        decl1 = ft1._get_declaration()
        assert decl1 is not None
        schema1 = decl1.parameters_json_schema or {}
        props1 = schema1.get("properties", {})
        assert "query" in props1
        assert "top_k" in props1
        assert "tool_context" not in props1

        decl2 = ft2._get_declaration()
        assert decl2 is not None
        schema2 = decl2.parameters_json_schema or {}
        props2 = schema2.get("properties", {})
        assert "chunk_ids" in props2
        assert "tool_context" not in props2
