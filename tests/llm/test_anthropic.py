"""Tests for the Anthropic-format LLM client.

Uses FakeTransport to mock HTTP at the transport seam — no pytest-httpx
dependency. Tests verify request/response parsing logic.
"""

import json

import pytest

from backend.llm.anthropic import AnthropicClient
from backend.llm.protocol import LLMError, Message, ToolDef
from tests.fakes import FakeTransport


# ── Fixture ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client() -> AnthropicClient:
    return AnthropicClient(
        model="test-model",
        base_url="https://api.test.com/v1",
        api_key="sk-test",
        max_tokens=1024,
    )


# ── Request body construction ────────────────────────────────────────────────


class TestRequestBody:
    def test_system_in_separate_field(self, client: AnthropicClient) -> None:
        body = client._build_body(
            messages=[Message(role="user", content="hi")],
            system="be concise",
            tools=None,
            stream=False,
        )
        assert body["model"] == "test-model"
        assert body["system"] == "be concise"
        assert body["max_tokens"] == 1024
        assert body["stream"] is False
        assert body["messages"] == [{"role": "user", "content": "hi"}]

    def test_no_system_when_none(self, client: AnthropicClient) -> None:
        body = client._build_body(
            messages=[Message(role="user", content="hi")],
            system=None,
            tools=None,
            stream=True,
        )
        assert body["stream"] is True
        assert "system" not in body

    def test_filters_system_messages(self, client: AnthropicClient) -> None:
        """Anthropic format puts system in a separate field, not messages."""
        body = client._build_body(
            messages=[
                Message(role="system", content="dup"),
                Message(role="user", content="hi"),
            ],
            system="real system",
            tools=None,
            stream=False,
        )
        assert body["system"] == "real system"
        assert len(body["messages"]) == 1  # system message removed
        assert body["messages"][0]["role"] == "user"

    def test_correct_headers(self, client: AnthropicClient) -> None:
        headers = client._headers()
        assert headers["x-api-key"] == "sk-test"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["content-type"] == "application/json"

    def test_includes_tools(self, client: AnthropicClient) -> None:
        """Tool definitions are serialised into the request body."""
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
        assert body["tools"][0]["name"] == "search"
        assert "input_schema" in body["tools"][0]


# ── Non-streaming generate ───────────────────────────────────────────────────


class TestGenerate:
    async def test_returns_content_and_usage(self) -> None:
        transport = FakeTransport.with_body(
            json.dumps({
                "content": [{"type": "text", "text": "Hello!"}],
                "usage": {"input_tokens": 5, "output_tokens": 10},
            }).encode()
        )
        client = AnthropicClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        response = await client.generate(
            messages=[Message(role="user", content="hi")]
        )
        assert response.content == "Hello!"
        assert response.usage is not None
        assert response.usage.input_tokens == 5
        assert response.usage.output_tokens == 10

    async def test_concatenates_multiple_text_blocks(self) -> None:
        transport = FakeTransport.with_body(
            json.dumps({
                "content": [
                    {"type": "text", "text": "Part 1. "},
                    {"type": "text", "text": "Part 2."},
                ],
            }).encode()
        )
        client = AnthropicClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        response = await client.generate(
            messages=[Message(role="user", content="hi")]
        )
        assert response.content == "Part 1. Part 2."

    async def test_raises_llm_error_on_4xx(self) -> None:
        transport = FakeTransport.with_error(
            status=401,
            body=json.dumps({"error": {"message": "Invalid API key"}}).encode(),
        )
        client = AnthropicClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        with pytest.raises(LLMError) as excinfo:
            await client.generate(
                messages=[Message(role="user", content="hi")]
            )
        assert excinfo.value.status == 401

    async def test_posts_to_correct_url(self) -> None:
        transport = FakeTransport.with_body(json.dumps({"content": []}).encode())
        client = AnthropicClient(
            model="m", base_url="https://api.test.com/v1", api_key="sk-test",
            transport=transport,
        )

        await client.generate(messages=[Message(role="user", content="hi")])

        assert len(transport.sent_requests) == 1
        url, _, _ = transport.sent_requests[0]
        assert url == "https://api.test.com/v1/messages"


# ── Streaming generate ───────────────────────────────────────────────────────


class TestGenerateStream:
    SSE_EVENTS = [
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}',
        "",
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}',
        "",
        'data: {"type":"message_delta","usage":{"input_tokens":3,"output_tokens":2}}',
        "",
        "data: [DONE]",
        "",
    ]

    async def test_yields_text_deltas(self) -> None:
        transport = FakeTransport.with_stream(["\n".join(self.SSE_EVENTS)])
        client = AnthropicClient(
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

    async def test_records_usage_from_message_delta(self) -> None:
        transport = FakeTransport.with_stream(["\n".join(self.SSE_EVENTS)])
        client = AnthropicClient(
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

    async def test_handles_message_start_event(self) -> None:
        """message_start can carry initial text in the content blocks."""
        events = [
            'data: {"type":"message_start","message":{"content":[{"type":"text","text":"Initial "}]}}',
            "",
            "data: [DONE]",
            "",
        ]
        transport = FakeTransport.with_stream(["\n".join(events)])
        client = AnthropicClient(
            model="m", base_url="https://api.test/v1", api_key="sk-test",
            transport=transport,
        )

        texts = []
        async for event in client.generate_stream(
            messages=[Message(role="user", content="hi")]
        ):
            if event.content:
                texts.append(event.content)

        assert texts == ["Initial "]

    async def test_raises_llm_error_on_4xx(self) -> None:
        transport = FakeTransport.with_error(
            status=429,
            body=json.dumps({"error": {"message": "Too many requests"}}).encode(),
        )
        client = AnthropicClient(
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
        client = AnthropicClient(
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
    def test_parses_text_delta(self) -> None:
        event = 'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}'
        result = AnthropicClient._parse_sse_event(event)
        assert result is not None
        assert result.content == "hi"
        assert result.usage is None

    def test_parses_message_start(self) -> None:
        event = 'data: {"type":"message_start","message":{"content":[{"type":"text","text":"init"}]}}'
        result = AnthropicClient._parse_sse_event(event)
        assert result is not None
        assert result.content == "init"

    def test_parses_usage_from_message_delta(self) -> None:
        event = 'data: {"type":"message_delta","usage":{"input_tokens":1,"output_tokens":2}}'
        result = AnthropicClient._parse_sse_event(event)
        assert result is not None
        assert result.content == ""
        assert result.usage is not None
        assert result.usage.input_tokens == 1
        assert result.usage.output_tokens == 2

    def test_handles_done_signal(self) -> None:
        result = AnthropicClient._parse_sse_event("data: [DONE]")
        assert result is None

    def test_handles_empty_event(self) -> None:
        result = AnthropicClient._parse_sse_event("")
        assert result is None

    def test_handles_malformed_json(self) -> None:
        result = AnthropicClient._parse_sse_event("data: {{{broken}")
        assert result is None

    def test_ignores_unknown_event_types(self) -> None:
        result = AnthropicClient._parse_sse_event('data: {"type":"ping"}')
        assert result is None
