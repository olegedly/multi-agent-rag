"""Tests for demo abuse-prevention middleware.

Three layers:
  1. Query validation (ChatGuard) — checks user message length & count
  2. Daily budget (ChatGuard) — checks token budget file
  3. End-to-end wiring in create_app()
"""

from datetime import date
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.corpus_config import CorporaConfig
from backend.main import create_app
from ag_ui.core.events import (
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from backend.middleware import BudgetStore, JsonFileBudget


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _noop_pipeline(messages, corpus_slug, **kwargs):
    """Fake pipeline that yields AG-UI events immediately — avoids LLM calls.

    Yields the minimal event sequence so ``EventEncoder.encode()`` can
    serialize it without errors.
    """
    ts = 1000000
    yield RunStartedEvent(thread_id="test-thread", run_id="test-run", timestamp=ts)
    yield TextMessageStartEvent(message_id="msg-1", role="assistant", timestamp=ts)
    yield TextMessageContentEvent(message_id="msg-1", delta="", timestamp=ts)
    yield TextMessageEndEvent(message_id="msg-1", timestamp=ts)
    yield RunFinishedEvent(
        thread_id="test-thread",
        run_id="test-run",
        timestamp=ts,
        finishReason="stop",  # type: ignore[call-arg]
        usage={"promptTokens": 0, "completionTokens": 0},  # type: ignore[call-arg]
    )


TEST_CORPORA = CorporaConfig.from_dicts([
    {"id": "eu-act-uuid", "slug": "eu-ai-act", "name": "EU AI Act",
     "description": "Test", "chunker": "markdown-heading",
     "documents": "corpora/eu-ai-act/**/*.md"},
])


# ── Budget File ──────────────────────────────────────────────────────────────


class TestFileBudget:
    """JsonFileBudget: auto-create, date-reset, read/write."""

    @pytest.fixture
    def tmp_budget(self, tmp_path) -> JsonFileBudget:
        return JsonFileBudget(path=str(tmp_path / "demo-budget.json"), daily_limit=100)

    def test_satisfies_budget_store_protocol(self, tmp_budget: JsonFileBudget) -> None:
        assert isinstance(tmp_budget, BudgetStore)

    def test_auto_creates_on_read(self, tmp_budget: JsonFileBudget) -> None:
        d, t = tmp_budget.read()
        assert t == 0
        assert d == date.today().isoformat()

    def test_increments_tokens(self, tmp_budget: JsonFileBudget) -> None:
        tmp_budget.add_tokens(30)
        _, t = tmp_budget.read()
        assert t == 30

    def test_accumulates_multiple_increments(self, tmp_budget: JsonFileBudget) -> None:
        tmp_budget.add_tokens(10)
        tmp_budget.add_tokens(20)
        tmp_budget.add_tokens(30)
        _, t = tmp_budget.read()
        assert t == 60

    def test_not_exhausted_when_under_limit(self, tmp_budget: JsonFileBudget) -> None:
        tmp_budget.add_tokens(50)
        assert not tmp_budget.is_exhausted()

    def test_exhausted_at_limit(self, tmp_budget: JsonFileBudget) -> None:
        tmp_budget.add_tokens(100)
        assert tmp_budget.is_exhausted()

    def test_exhausted_over_limit(self, tmp_budget: JsonFileBudget) -> None:
        tmp_budget.add_tokens(200)
        assert tmp_budget.is_exhausted()

    def test_preserves_data_through_read_write_cycle(self, tmp_budget: JsonFileBudget) -> None:
        tmp_budget.add_tokens(42)
        tmp_budget.add_tokens(1)
        _, t = tmp_budget.read()
        assert t == 43


# ── Budget Middleware ─────────────────────────────────────────────────────────


class TestBudgetMiddleware:
    """Daily token budget check via ChatGuard (fires before routing)."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
        # Stub the pipeline so it doesn't actually call an LLM
        monkeypatch.setattr("backend.main.run_pipeline", _noop_pipeline)
        app = create_app(
            settings=Settings(
                demo_daily_budget_tokens=50,
                demo_budget_file=str(tmp_path / "demo-budget.json"),
            ),
            corpora_config=TEST_CORPORA,
        )
        with TestClient(app) as c:
            yield c

    def _chat_payload(self) -> dict:
        return {"messages": [{"role": "user", "content": "hello"}]}

    def test_allows_request_when_budget_available(self, client: TestClient) -> None:
        response = client.post("/api/chat/eu-ai-act", json=self._chat_payload())
        assert response.status_code == 200

    def test_returns_429_when_budget_exhausted(self, client: TestClient, tmp_path) -> None:
        budget = JsonFileBudget(path=str(tmp_path / "demo-budget.json"), daily_limit=50)
        budget.add_tokens(100)

        response = client.post("/api/chat/eu-ai-act", json=self._chat_payload())
        assert response.status_code == 429
        assert "budget" in response.json()["detail"].lower()

    def test_health_check_not_blocked_by_budget(self, client: TestClient) -> None:
        assert client.get("/api/health").status_code == 200


class TestBudgetDevBypass:
    """When DEMO_DISABLE_BUDGET=true, budget check is skipped."""

    def test_allows_request_when_exhausted(self, tmp_path, monkeypatch) -> None:
        budget = JsonFileBudget(path=str(tmp_path / "budget.json"), daily_limit=50)
        budget.add_tokens(100)

        monkeypatch.setattr("backend.main.run_pipeline", _noop_pipeline)

        app = create_app(
            settings=Settings(
                demo_disable_budget=True,
                demo_budget_file=str(tmp_path / "budget.json"),
            ),
            corpora_config=TEST_CORPORA,
        )
        with TestClient(app) as c:
            response = c.post("/api/chat/eu-ai-act", json={"messages": [{"role": "user", "content": "hello"}]})
            assert response.status_code == 200

    def test_budget_check_skipped_when_disabled(self, tmp_path) -> None:
        app = create_app(
            settings=Settings(demo_disable_budget=True, demo_budget_file=str(tmp_path / "budget.json")),
            corpora_config=TEST_CORPORA,
        )
        mids = [m.cls for m in app.user_middleware]
        from backend.middleware import ChatGuard
        assert ChatGuard in mids

    def test_query_still_active_when_budget_disabled(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("backend.main.run_pipeline", _noop_pipeline)

        app = create_app(
            settings=Settings(demo_disable_budget=True, demo_max_query_length=10, demo_budget_file=str(tmp_path / "budget.json")),
            corpora_config=TEST_CORPORA,
        )
        with TestClient(app) as c:
            response = c.post("/api/chat/eu-ai-act", json={"messages": [{"role": "user", "content": "x" * 11}]})
            assert response.status_code == 422


# ── Query Validation ─────────────────────────────────────────────────────────


class TestQueryValidation:
    """Query length and count validation via ChatGuard."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
        monkeypatch.setattr("backend.main.run_pipeline", _noop_pipeline)
        app = create_app(
            settings=Settings(
                demo_max_query_length=10,
                demo_max_user_messages=3,
                demo_budget_file=str(tmp_path / "budget.json"),
            ),
            corpora_config=TEST_CORPORA,
        )
        with TestClient(app) as c:
            yield c

    def test_short_query_accepted(self, client: TestClient) -> None:
        response = client.post("/api/chat/eu-ai-act", json={"messages": [{"role": "user", "content": "hi"}]})
        assert response.status_code == 200

    def test_long_query_rejected(self, client: TestClient) -> None:
        response = client.post("/api/chat/eu-ai-act", json={"messages": [{"role": "user", "content": "x" * 11}]})
        assert response.status_code == 422

    def test_boundary_length_accepted(self, client: TestClient) -> None:
        response = client.post("/api/chat/eu-ai-act", json={"messages": [{"role": "user", "content": "x" * 10}]})
        assert response.status_code == 200

    def test_too_many_messages_rejected(self, client: TestClient) -> None:
        msgs = [{"role": "user", "content": "hi"} for _ in range(4)]
        response = client.post("/api/chat/eu-ai-act", json={"messages": msgs})
        assert response.status_code == 422

    def test_at_limit_messages_accepted(self, client: TestClient) -> None:
        msgs = [{"role": "user", "content": "hi"} for _ in range(3)]
        response = client.post("/api/chat/eu-ai-act", json={"messages": msgs})
        assert response.status_code == 200

    def test_assistant_messages_not_counted(self, client: TestClient) -> None:
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "x" * 100},
        ]
        response = client.post("/api/chat/eu-ai-act", json={"messages": msgs})
        assert response.status_code == 200

    def test_health_check_not_blocked(self, client: TestClient) -> None:
        assert client.get("/api/health").status_code == 200
