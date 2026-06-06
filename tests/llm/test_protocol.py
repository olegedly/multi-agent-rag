"""Tests for the LLM abstraction protocol types.

All tests here are pure-data — no I/O, no mocking.
"""

import pytest

from backend.llm.protocol import LLMClient, LLMError, LLMResponse, Message, Usage


# ── Message ──────────────────────────────────────────────────────────────────


class TestMessage:
    def test_constructs_with_role_and_content(self) -> None:
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_supports_system_role(self) -> None:
        msg = Message(role="system", content="be helpful")
        assert msg.role == "system"

    def test_supports_assistant_role(self) -> None:
        msg = Message(role="assistant", content="I am an AI")
        assert msg.role == "assistant"


# ── Usage ────────────────────────────────────────────────────────────────────


class TestUsage:
    def test_defaults_to_zero(self) -> None:
        u = Usage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0

    def test_accepts_positive_values(self) -> None:
        u = Usage(input_tokens=10, output_tokens=20)
        assert u.input_tokens == 10
        assert u.output_tokens == 20


# ── LLMResponse ──────────────────────────────────────────────────────────────


class TestLLMResponse:
    def test_constructs_with_content_only(self) -> None:
        r = LLMResponse(content="hello")
        assert r.content == "hello"
        assert r.finish_reason is None
        assert r.usage is None

    def test_accepts_finish_reason_and_usage(self) -> None:
        u = Usage(input_tokens=5, output_tokens=15)
        r = LLMResponse(content="hello", finish_reason="stop", usage=u)
        assert r.finish_reason == "stop"
        assert r.usage is not None
        assert r.usage.input_tokens == 5


# ── LLMError ─────────────────────────────────────────────────────────────────


class TestLLMError:
    def test_constructs_with_status_and_message(self) -> None:
        err = LLMError(status=401, message="unauthorized")
        assert err.status == 401
        assert "unauthorized" in str(err)

    def test_includes_details_in_message(self) -> None:
        err = LLMError(status=429, message="rate limited", details="retry after 5s")
        msg = str(err)
        assert "rate limited" in msg
        assert "retry after 5s" in msg

    def test_is_exception(self) -> None:
        err = LLMError(status=500, message="server error")
        assert isinstance(err, Exception)


# ── LLMClient (abstract) ─────────────────────────────────────────────────────


class TestLLMClient:
    def test_cannot_instantiate_abstract(self) -> None:
        """LLMClient is an ABC — instantiating it directly must raise."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            LLMClient()  # type: ignore[abstract]
