"""Tests for demo abuse-prevention middleware.

Three layers:
  1. Query validation (FastAPI middleware) — checks user message length & count
  2. Daily budget (ASGI middleware) — checks token budget file
  3. End-to-end wiring in create_app()

All tests inject FakeLLMClient so no real HTTP calls are made.
"""

from datetime import date

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.middleware import BudgetFile
from tests.fakes import FakeLLMClient


# ── Budget File Helpers ──────────────────────────────────────────────────────


class TestBudgetFile:
    """BudgetFile: auto-create, date-reset, read/write.

    Uses a temp directory for isolation — no shared state between tests.
    """

    @pytest.fixture
    def tmp_budget(self, tmp_path) -> BudgetFile:
        return BudgetFile(path=str(tmp_path / "demo-budget.json"), daily_limit=100)

    def test_auto_creates_on_read(self, tmp_budget: BudgetFile) -> None:
        """Reading a non-existent file creates it with today's date and 0 tokens."""
        d, t = tmp_budget.read()
        assert t == 0
        assert d == date.today().isoformat()

    def test_increments_tokens(self, tmp_budget: BudgetFile) -> None:
        tmp_budget.add_tokens(30)
        _, t = tmp_budget.read()
        assert t == 30

    def test_accumulates_multiple_increments(self, tmp_budget: BudgetFile) -> None:
        tmp_budget.add_tokens(10)
        tmp_budget.add_tokens(25)
        _, t = tmp_budget.read()
        assert t == 35

    def test_not_exhausted_when_under_limit(self, tmp_budget: BudgetFile) -> None:
        tmp_budget.add_tokens(50)
        assert not tmp_budget.is_exhausted()

    def test_exhausted_at_limit(self, tmp_budget: BudgetFile) -> None:
        tmp_budget.add_tokens(100)
        assert tmp_budget.is_exhausted()

    def test_exhausted_over_limit(self, tmp_budget: BudgetFile) -> None:
        tmp_budget.add_tokens(150)
        assert tmp_budget.is_exhausted()

    def test_preserves_data_through_read_write_cycle(self, tmp_budget: BudgetFile) -> None:
        tmp_budget.add_tokens(42)
        tmp_budget.add_tokens(1)
        d, t = tmp_budget.read()
        assert t == 43
        assert d == date.today().isoformat()


# ── Budget Middleware ────────────────────────────────────────────────────────


class TestBudgetMiddleware:
    """Layer 2: ASGI middleware checks daily token budget and returns 429 when exhausted."""

    @pytest.fixture
    def client(self, tmp_path) -> Generator[TestClient, None, None]:
        app = create_app(
            llm_client=FakeLLMClient(),
            settings=Settings(
                demo_daily_budget_tokens=50,
                demo_budget_file=str(tmp_path / "demo-budget.json"),
            ),
        )
        with TestClient(app) as c:
            yield c

    def _chat_payload(self) -> dict:
        return {
            "thread_id": "test-thread",
            "run_id": "test-run",
            "state": {},
            "messages": [{"id": "msg-0", "role": "user", "content": "hello"}],
            "tools": [],
            "context": [],
            "forwarded_props": {},
        }

    def test_allows_request_when_budget_available(self, client: TestClient) -> None:
        payload = self._chat_payload()
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200

    def test_budget_increments_after_chat(self, client: TestClient, tmp_path) -> None:
        """The usage_callback should increment the budget file after a response."""
        payload = self._chat_payload()
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200

        # Check the budget was incremented
        budget = BudgetFile(
            path=str(tmp_path / "demo-budget.json"),
            daily_limit=50,
        )
        _, used = budget.read()
        # FakeLLMClient returns Usage(input_tokens=10, output_tokens=len("Fake response"))
        assert used == 10 + len("Fake response")  # 10 + 12 = 22

    def test_returns_429_when_budget_exhausted(self, client: TestClient, tmp_path) -> None:
        """Pre-seed the budget file to be over the limit."""
        budget = BudgetFile(
            path=str(tmp_path / "demo-budget.json"),
            daily_limit=50,
        )
        budget.add_tokens(100)  # over limit

        payload = self._chat_payload()
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 429
        data = response.json()
        assert "budget" in data["detail"].lower()

    def test_budget_not_incremented_on_rejected_request(self, client: TestClient, tmp_path) -> None:
        """When budget is exhausted, the usage_callback should not fire."""
        budget = BudgetFile(
            path=str(tmp_path / "demo-budget.json"),
            daily_limit=50,
        )
        budget.add_tokens(100)  # over limit

        payload = self._chat_payload()
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 429

        # Budget should still be exactly 100 (no additional increment)
        _, used = budget.read()
        assert used == 100

    def test_health_check_not_blocked_by_budget(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200


class TestBudgetDevBypass:
    """When DEMO_DISABLE_BUDGET=true, budget middleware is skipped entirely."""

    def test_allows_request_when_exhausted(self, tmp_path) -> None:
        """Even with exhausted budget, disabled mode allows request through."""
        # Pre-seed exhausted budget
        budget = BudgetFile(path=str(tmp_path / "budget.json"), daily_limit=50)
        budget.add_tokens(100)

        app = create_app(
            llm_client=FakeLLMClient(),
            settings=Settings(
                demo_disable_budget=True,
                demo_daily_budget_tokens=50,
                demo_budget_file=str(tmp_path / "budget.json"),
            ),
        )
        with TestClient(app) as c:
            payload = {
                "thread_id": "test",
                "run_id": "test",
                "state": {},
                "messages": [{"id": "msg-0", "role": "user", "content": "hello"}],
                "tools": [],
                "context": [],
                "forwarded_props": {},
            }
            response = c.post("/api/chat", json=payload)
            assert response.status_code == 200

    def test_middleware_not_registered_when_disabled(self, tmp_path) -> None:
        """When disabled, no BudgetMiddleware instance is added."""
        app = create_app(
            llm_client=FakeLLMClient(),
            settings=Settings(
                demo_disable_budget=True,
                demo_budget_file=str(tmp_path / "budget.json"),
            ),
        )
        # Check no BudgetMiddleware in the user middleware stack
        mids = [m.__class__.__name__ for m in app.user_middleware]
        assert "BudgetMiddleware" not in mids

    def test_query_still_active_when_budget_disabled(self, tmp_path) -> None:
        """Query validation still runs even with budget disabled."""
        app = create_app(
            llm_client=FakeLLMClient(),
            settings=Settings(
                demo_disable_budget=True,
                demo_max_query_length=10,
                demo_budget_file=str(tmp_path / "budget.json"),
            ),
        )
        with TestClient(app) as c:
            payload = {
                "thread_id": "test",
                "run_id": "test",
                "state": {},
                "messages": [{"id": "msg-0", "role": "user", "content": "x" * 11}],
                "tools": [],
                "context": [],
                "forwarded_props": {},
            }
            response = c.post("/api/chat", json=payload)
            assert response.status_code == 422


# ── Query Validation ─────────────────────────────────────────────────────────


class TestQueryValidation:
    """Layer 3: FastAPI middleware that validates user message length and count.

    Every user message in the request body must be ≤ 500 characters
    (default; configurable via DEMO_MAX_QUERY_LENGTH).
    Total user messages must be ≤ 50 (DEMO_MAX_USER_MESSAGES).
    """

    @pytest.fixture
    def client(self, tmp_path) -> Generator[TestClient, None, None]:
        app = create_app(
            llm_client=FakeLLMClient(),
            settings=Settings(
                demo_max_query_length=10,
                demo_max_user_messages=3,
                demo_budget_file=str(tmp_path / "budget.json"),
            ),
        )
        with TestClient(app) as c:
            yield c

    def _chat_payload(self, messages: list[dict]) -> dict:
        """Build a minimal AG-UI chat payload."""
        return {
            "thread_id": "test-thread",
            "run_id": "test-run",
            "state": {},
            "messages": [
                {"id": f"msg-{i}", "role": "user", "content": m["content"], **({} if "parts" not in m else {"parts": m["parts"]})}
                for i, m in enumerate(messages)
            ],
            "tools": [],
            "context": [],
            "forwarded_props": {},
        }

    def test_short_query_accepted(self, client: TestClient) -> None:
        """A single short user message is fine."""
        payload = self._chat_payload([{"content": "hi"}])
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200, response.text

    def test_long_query_rejected(self, client: TestClient) -> None:
        """A user message exceeding max length returns 422."""
        payload = self._chat_payload([{"content": "x" * 11}])
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert "query" in data["detail"].lower() or "message" in data["detail"].lower()

    def test_boundary_length_accepted(self, client: TestClient) -> None:
        """A user message at exactly the max length is accepted."""
        payload = self._chat_payload([{"content": "x" * 10}])
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200

    def test_too_many_messages_rejected(self, client: TestClient) -> None:
        """More than max_user_messages returns 422."""
        msgs = [{"content": "hi"} for _ in range(4)]
        payload = self._chat_payload(msgs)
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert "messages" in data["detail"].lower()

    def test_at_limit_messages_accepted(self, client: TestClient) -> None:
        """Exactly max_user_messages is accepted."""
        msgs = [{"content": "hi"} for _ in range(3)]
        payload = self._chat_payload(msgs)
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200

    def test_assistant_messages_not_counted(self, client: TestClient) -> None:
        """Only user-role messages are checked for length and count."""
        msgs = [
            {"content": "hi"},
            {"role": "assistant", "content": "x" * 100},  # long but not user
        ]
        payload = self._chat_payload(msgs)
        # Override roles
        payload["messages"][1]["role"] = "assistant"
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200

    def test_health_check_not_blocked(self, client: TestClient) -> None:
        """Non-chat endpoints should not be subject to query validation."""
        response = client.get("/api/health")
        assert response.status_code == 200
