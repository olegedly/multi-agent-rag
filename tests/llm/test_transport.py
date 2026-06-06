"""Tests for the HTTP transport layer.

Only these tests use ``pytest-httpx`` — after the refactor, the
``OpenAIClient`` and ``AnthropicClient`` tests inject a ``FakeTransport``
and never hit the wire.
"""

import json

import httpx
import pytest

from backend.llm.protocol import LLMError
from backend.llm.transport import HttpTransport, _parse_error_body


# ── _parse_error_body (hoisted from openai/anthropic clients) ────────────────


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


# ── HttpTransport: send (non-streaming) ──────────────────────────────────────


class TestSend:
    async def test_returns_response_on_success(
        self, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            json={"content": "ok"},
            headers={"content-type": "application/json"},
        )
        transport = HttpTransport(timeout=30)
        try:
            response = await transport.send(
                url="https://example.com/v1/messages",
                headers={"auth": "Bearer x"},
                json_body={"model": "test", "messages": []},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["content"] == "ok"
        finally:
            await transport.close()

    async def test_posts_to_correct_url(
        self, httpx_mock
    ) -> None:
        httpx_mock.add_response(json={})
        transport = HttpTransport()
        try:
            await transport.send(
                url="https://api.test/v1/completions",
                headers={"auth": "Bearer x"},
                json_body={"key": "val"},
            )
            request = httpx_mock.get_request()
            assert request is not None
            assert str(request.url) == "https://api.test/v1/completions"
        finally:
            await transport.close()

    async def test_raises_llm_error_on_4xx(
        self, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            status_code=401,
            json={"error": {"message": "Invalid API key"}},
        )
        transport = HttpTransport()
        try:
            with pytest.raises(LLMError) as excinfo:
                await transport.send(
                    url="https://example.com/v1/messages",
                    headers={"auth": "Bearer x"},
                    json_body={},
                )
            assert excinfo.value.status == 401
            assert "Invalid API key" in str(excinfo.value)
        finally:
            await transport.close()


# ── HttpTransport: send_stream (streaming) ───────────────────────────────────


class TestSendStream:
    async def test_yields_text_chunks(self, httpx_mock) -> None:
        httpx_mock.add_response(
            text="Hello\nWorld",
            headers={"content-type": "text/event-stream"},
        )
        transport = HttpTransport()
        try:
            chunks: list[str] = []
            async for chunk in transport.send_stream(
                url="https://example.com/v1/messages",
                headers={"auth": "Bearer x"},
                json_body={},
            ):
                chunks.append(chunk)
            assert chunks == ["Hello\nWorld"]
        finally:
            await transport.close()

    async def test_raises_llm_error_on_4xx(self, httpx_mock) -> None:
        httpx_mock.add_response(
            status_code=429,
            json={"error": {"message": "Too many requests"}},
        )
        transport = HttpTransport()
        try:
            with pytest.raises(LLMError) as excinfo:
                async for _ in transport.send_stream(
                    url="https://example.com/v1/messages",
                    headers={"auth": "Bearer x"},
                    json_body={},
                ):
                    pass
            assert excinfo.value.status == 429
        finally:
            await transport.close()

    async def test_posts_to_correct_url(self, httpx_mock) -> None:
        httpx_mock.add_response(text="")
        transport = HttpTransport()
        try:
            async for _ in transport.send_stream(
                url="https://api.test/v1/stream",
                headers={"auth": "Bearer x"},
                json_body={"stream": True},
            ):
                pass
            request = httpx_mock.get_request()
            assert request is not None
            assert str(request.url) == "https://api.test/v1/stream"
        finally:
            await transport.close()

    async def test_close_is_idempotent(self) -> None:
        transport = HttpTransport()
        await transport.close()
        await transport.close()  # should not raise
