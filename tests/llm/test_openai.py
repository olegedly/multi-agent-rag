"""Tests for the OpenAI-format LLM client.

Uses FakeTransport to mock HTTP at the transport seam — no pytest-httpx
dependency. Tests verify request/response parsing logic.
"""

import json

import pytest

from backend.llm.openai import OpenAIClient
from backend.llm.protocol import LLMError, Message
from tests.fakes import FakeTransport


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
            tools=None,
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
            tools=None,
            stream=True,
        )
        assert body["stream"] is True
        assert len(body["messages"]) == 1

    def test_filters_duplicate_system_message(self, client: OpenAIClient) -> None:
        """Client ensures system is only in the top-level field, not messages."""
        body = client._build_body(
            messages=[Message(role="system", content="dup"), Message(role="user", content="hi")],
            system="real system",
            tools=None,
            stream=False,
        )
        roles = [m["role"] for m in body["messages"]]
        assert roles == ["system", "user"]  # system from kwarg, user from messages

    def test_includes_tools(self, client: OpenAIClient) -> None:
        """Tool definitions are serialised into the request body."""
        from backend.llm.protocol import ToolDef
        body = client._build_body(
            messages=[Message(role="user", content="hi")],
            system=None,
            tools=[
                ToolDef(name="search", description="Search the corpus", parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                }),
            ],
            stream=False,
        )
        assert "tools" in body
        assert len(body["tools"]) == 1
        assert body["tools"][0]["function"]["name"] == "search"


# ── Non-streaming generate ───────────────────────────────────────────────────


class TestGenerate:
    async def test_returns_content_and_usage(self) -> None:
        transport = FakeTransport.with_body(
            json.dumps({
                "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10},
            }).encode()
        )
        client = OpenAIClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        response = await client.generate(
            messages=[Message(role="user", content="hi")]
        )
        assert response.content == "Hello!"
        assert response.finish_reason == "stop"
        assert response.usage is not None
        assert response.usage.input_tokens == 5
        assert response.usage.output_tokens == 10

    async def test_raises_llm_error_on_4xx(self) -> None:
        transport = FakeTransport.with_error(
            status=401,
            body=json.dumps({"error": {"message": "Invalid API key"}}).encode(),
        )
        client = OpenAIClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        with pytest.raises(LLMError) as excinfo:
            await client.generate(
                messages=[Message(role="user", content="hi")]
            )
        assert excinfo.value.status == 401
        assert "Invalid API key" in str(excinfo.value)

    async def test_posts_to_correct_url(self) -> None:
        transport = FakeTransport.with_body(
            json.dumps({"choices": [{"message": {"content": ""}}]}).encode()
        )
        client = OpenAIClient(
            model="m", base_url="https://api.test.com/v1", api_key="sk-test",
            transport=transport,
        )

        await client.generate(messages=[Message(role="user", content="hi")])

        assert len(transport.sent_requests) == 1
        url, headers, _body = transport.sent_requests[0]
        assert url == "https://api.test.com/v1/chat/completions"
        assert headers["authorization"] == "Bearer sk-test"
        assert headers["content-type"] == "application/json"


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

    async def test_yields_text_deltas(self) -> None:
        transport = FakeTransport.with_stream(["\n".join(self.SSE_EVENTS)])
        client = OpenAIClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        texts = []
        async for event in client.generate_stream(
            messages=[Message(role="user", content="hi")]
        ):
            if event.content:
                texts.append(event.content)

        assert texts == ["Hello", " world"]

    async def test_records_usage_from_final_event(self) -> None:
        transport = FakeTransport.with_stream(["\n".join(self.SSE_EVENTS)])
        client = OpenAIClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        last_usage = None
        async for event in client.generate_stream(
            messages=[Message(role="user", content="hi")]
        ):
            if event.usage is not None:
                last_usage = event.usage

        assert last_usage is not None
        assert last_usage.input_tokens == 3
        assert last_usage.output_tokens == 2

    async def test_raises_llm_error_on_4xx(self) -> None:
        transport = FakeTransport.with_error(
            status=429,
            body=json.dumps({"error": {"message": "Too many requests"}}).encode(),
        )
        client = OpenAIClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        with pytest.raises(LLMError) as excinfo:
            async for _ in client.generate_stream(
                messages=[Message(role="user", content="hi")]
            ):
                pass
        assert excinfo.value.status == 429

    async def test_handles_empty_stream(self) -> None:
        transport = FakeTransport.with_stream(["data: [DONE]\n\n"])
        client = OpenAIClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        events = []
        async for event in client.generate_stream(
            messages=[Message(role="user", content="hi")]
        ):
            events.append(event)

        assert events == []


# ── SSE parser (static) ──────────────────────────────────────────────────────


class TestParseSseEvent:
    def test_parses_content_delta(self) -> None:
        event = 'data: {"choices":[{"delta":{"content":"hi"},"index":0}]}'
        result = OpenAIClient._parse_sse_event(event)
        assert result is not None
        assert result.content == "hi"
        assert result.usage is None

    def test_parses_usage(self) -> None:
        event = 'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":1,"completion_tokens":2}}'
        result = OpenAIClient._parse_sse_event(event)
        assert result is not None
        assert result.content == ""
        assert result.usage is not None
        assert result.usage.input_tokens == 1
        assert result.usage.output_tokens == 2

    def test_handles_done_signal(self) -> None:
        result = OpenAIClient._parse_sse_event("data: [DONE]")
        assert result is None

    def test_handles_empty_event(self) -> None:
        result = OpenAIClient._parse_sse_event("")
        assert result is None

    def test_handles_malformed_json(self) -> None:
        result = OpenAIClient._parse_sse_event("data: {{broken}")
        assert result is None

    def test_extracts_data_line(self) -> None:
        """Ignores event: lines and only reads data: lines."""
        event_block = 'event: foo\ndata: {"choices":[{"delta":{"content":"ok"}}]}'
        result = OpenAIClient._parse_sse_event(event_block)
        assert result is not None
        assert result.content == "ok"
