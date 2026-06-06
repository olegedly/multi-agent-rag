"""Tests for the OpenAI-format LLM client.

Uses pytest-httpx to mock HTTP responses at the wire level so we can
verify request shapes and SSE parsing without a real endpoint.
"""

import json

import pytest

from backend.llm.openai import OpenAIClient, _parse_error_body
from backend.llm.protocol import LLMError, Message


# ── Fixture ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client() -> OpenAIClient:
    return OpenAIClient(
        model="test-model",
        base_url="https://api.test.com/v1",
        api_key="sk-test",
        max_tokens=1024,
    )


# ── Request body construction ────────────────────────────────────────────────


class TestRequestBody:
    def test_includes_system_message(self, client: OpenAIClient) -> None:
        body = client._build_body(
            messages=[Message(role="user", content="hi")],
            system="be concise",
            stream=False,
        )
        assert body["model"] == "test-model"
        assert body["max_tokens"] == 1024
        assert body["stream"] is False
        assert body["messages"][0] == {"role": "system", "content": "be concise"}
        assert body["messages"][1] == {"role": "user", "content": "hi"}

    def test_no_system_when_none(self, client: OpenAIClient) -> None:
        body = client._build_body(
            messages=[Message(role="user", content="hi")],
            system=None,
            stream=True,
        )
        assert body["stream"] is True
        assert len(body["messages"]) == 1

    def test_filters_duplicate_system_message(self, client: OpenAIClient) -> None:
        """Client ensures system is only in the top-level field, not messages."""
        body = client._build_body(
            messages=[Message(role="system", content="dup"), Message(role="user", content="hi")],
            system="real system",
            stream=False,
        )
        roles = [m["role"] for m in body["messages"]]
        assert roles == ["system", "user"]  # system from kwarg, user from messages


# ── Non-streaming generate ───────────────────────────────────────────────────


class TestGenerate:
    async def test_returns_content_and_usage(
        self, client: OpenAIClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            json={
                "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10},
            }
        )

        response = await client.generate(
            messages=[Message(role="user", content="hi")]
        )
        assert response.content == "Hello!"
        assert response.finish_reason == "stop"
        assert response.usage is not None
        assert response.usage.input_tokens == 5
        assert response.usage.output_tokens == 10

    async def test_raises_llm_error_on_4xx(
        self, client: OpenAIClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            status_code=401,
            json={"error": {"message": "Invalid API key"}},
        )

        with pytest.raises(LLMError) as excinfo:
            await client.generate(
                messages=[Message(role="user", content="hi")]
            )
        assert excinfo.value.status == 401
        assert "Invalid API key" in str(excinfo.value)

    async def test_posts_to_correct_url(
        self, client: OpenAIClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(json={"choices": [{"message": {"content": ""}}]})

        await client.generate(messages=[Message(role="user", content="hi")])

        request = httpx_mock.get_request()
        assert request is not None
        assert str(request.url) == "https://api.test.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-test"
        assert request.headers["content-type"] == "application/json"


# ── Streaming generate ───────────────────────────────────────────────────────


class TestGenerateStream:
    SSE_EVENTS = [
        'data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}',
        "",
        'data: {"choices":[{"delta":{"content":" world"},"index":0}]}',
        "",
        'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":3,"completion_tokens":2}}',
        "",
        "data: [DONE]",
        "",
    ]

    async def test_yields_text_deltas(
        self, client: OpenAIClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            text="\n".join(self.SSE_EVENTS),
            headers={"content-type": "text/event-stream"},
        )

        deltas = []
        async for chunk in client.generate_stream(
            messages=[Message(role="user", content="hi")]
        ):
            deltas.append(chunk)

        assert deltas == ["Hello", " world"]

    async def test_records_usage_from_final_event(
        self, client: OpenAIClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            text="\n".join(self.SSE_EVENTS),
        )

        async for _ in client.generate_stream(
            messages=[Message(role="user", content="hi")]
        ):
            pass

        assert client.last_usage is not None
        assert client.last_usage.input_tokens == 3
        assert client.last_usage.output_tokens == 2

    async def test_raises_llm_error_on_4xx(
        self, client: OpenAIClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            status_code=429,
            json={"error": {"message": "Too many requests"}},
        )

        with pytest.raises(LLMError) as excinfo:
            async for _ in client.generate_stream(
                messages=[Message(role="user", content="hi")]
            ):
                pass
        assert excinfo.value.status == 429

    async def test_handles_empty_stream(
        self, client: OpenAIClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(text="data: [DONE]\n\n")

        deltas = []
        async for chunk in client.generate_stream(
            messages=[Message(role="user", content="hi")]
        ):
            deltas.append(chunk)

        assert deltas == []


# ── SSE parser (static) ──────────────────────────────────────────────────────


class TestParseSseEvent:
    def test_parses_content_delta(self) -> None:
        event = 'data: {"choices":[{"delta":{"content":"hi"},"index":0}]}'
        deltas, usage = OpenAIClient._parse_sse_event(event)
        assert deltas == ["hi"]
        assert usage is None

    def test_parses_usage(self) -> None:
        event = 'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":1,"completion_tokens":2}}'
        deltas, usage = OpenAIClient._parse_sse_event(event)
        assert deltas == []
        assert usage is not None
        assert usage.input_tokens == 1
        assert usage.output_tokens == 2

    def test_handles_done_signal(self) -> None:
        deltas, usage = OpenAIClient._parse_sse_event("data: [DONE]")
        assert deltas == []
        assert usage is None

    def test_handles_empty_event(self) -> None:
        deltas, usage = OpenAIClient._parse_sse_event("")
        assert deltas == []
        assert usage is None

    def test_handles_malformed_json(self) -> None:
        deltas, usage = OpenAIClient._parse_sse_event("data: {{broken}")
        assert deltas == []
        assert usage is None

    def test_extracts_data_line(self) -> None:
        """Ignores event: lines and only reads data: lines."""
        event_block = 'event: foo\ndata: {"choices":[{"delta":{"content":"ok"}}]}'
        deltas, usage = OpenAIClient._parse_sse_event(event_block)
        assert deltas == ["ok"]


# ── Error body parser ────────────────────────────────────────────────────────


class TestParseErrorBody:
    def test_extracts_message_from_error_dict(self) -> None:
        body = json.dumps({"error": {"message": "bad request"}}).encode()
        assert _parse_error_body(body) == "bad request"

    def test_falls_back_to_string_on_non_dict_error(self) -> None:
        body = json.dumps({"error": "just a string"}).encode()
        assert _parse_error_body(body) == "just a string"

    def test_handles_bad_json(self) -> None:
        body = b"<html>not json</html>"
        result = _parse_error_body(body)
        assert "not json" in result

    def test_truncates_long_body(self) -> None:
        body = b"x" * 1000
        result = _parse_error_body(body)
        assert len(result) == 500
