"""Fake LLM client and helpers for testing.

Mocks the LLMClient abstract interface so all business-logic tests
exercise the same seam that production code uses — no HTTP mocking
libraries needed outside the concrete client tests.
"""

import json
from typing import AsyncIterable

from backend.llm.protocol import LLMClient, LLMResponse, Message, Usage


class FakeResponse:
    """Duck-typed httpx.Response for tests."""

    def __init__(self, status_code: int, _body: bytes):
        self.status_code = status_code
        self.__body = _body

    def json(self):
        return json.loads(self.__body)


class FakeTransport:
    """A fake HTTP transport for testing LLM clients.

    Pre-records response bodies (plain for non-streaming, chunk-lists for
    streaming) so that ``OpenAIClient`` / ``AnthropicClient`` tests can
    exercise request/response parsing without ``pytest-httpx``.
    """

    def __init__(self, status: int = 200, body: bytes | None = None):
        self.status = status
        self._body = body if body is not None else b'{"content": "ok"}'
        self.stream_chunks: list[str] | None = None
        self.sent_requests: list[tuple[str, dict, dict]] = []  # (url, headers, json_body)

    @classmethod
    def with_body(cls, body: bytes, status: int = 200) -> "FakeTransport":
        return cls(status=status, body=body)

    @classmethod
    def with_stream(cls, chunks: list[str], status: int = 200) -> "FakeTransport":
        t = cls(status=status)
        t.stream_chunks = chunks
        return t

    @classmethod
    def with_error(cls, status: int, body: bytes | None = None) -> "FakeTransport":
        if body is None:
            body = json.dumps({"error": {"message": "API error"}}).encode()
        return cls(status=status, body=body)

    async def send(
        self, url: str, headers: dict, json_body: dict
    ) -> FakeResponse:
        self.sent_requests.append((url, headers, json_body))
        if self.status >= 400:
            from backend.llm.protocol import LLMError

            raise LLMError(status=self.status, message="API error", details=self._body.decode())
        return FakeResponse(status_code=self.status, _body=self._body)

    async def send_stream(self, url: str, headers: dict, json_body: dict):
        self.sent_requests.append((url, headers, json_body))
        if self.status >= 400:
            from backend.llm.protocol import LLMError

            raise LLMError(status=self.status, message="API error")
        for chunk in (self.stream_chunks or []):
            yield chunk

    async def close(self) -> None:
        pass


class FakeLLMClient(LLMClient):
    """A fake LLM client with deterministic responses.

    Cycles through ``responses`` in order.  For streaming, yields one
    character at a time so callers can observe intermediate deltas.
    """

    def __init__(self, responses: list[str] | None = None):
        self.model = "fake-model"
        self.responses = responses or ["Fake response"]
        self._call_index = 0
        self.last_usage: Usage | None = None

    def _next_response(self) -> str:
        text = self.responses[self._call_index % len(self.responses)]
        self._call_index += 1
        self.last_usage = Usage(input_tokens=10, output_tokens=len(text))
        return text

    async def generate(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        text = self._next_response()
        return LLMResponse(content=text, usage=self.last_usage)

    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> AsyncIterable[str]:
        text = self._next_response()
        for char in text:
            yield char


class CollectingLLMClient(LLMClient):
    """Records every call for assertion; always returns the same response.

    Useful when a test needs to inspect what messages / system prompt
    were sent to the LLM.
    """

    def __init__(self, response: str = "collected"):
        self.model = "collector"
        self.calls: list[tuple[list[Message], str | None]] = []
        self.last_usage: Usage | None = None
        self._response = response

    async def generate(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        self.calls.append((messages, system))
        self.last_usage = Usage(input_tokens=5, output_tokens=len(self._response))
        return LLMResponse(content=self._response, usage=self.last_usage)

    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> AsyncIterable[str]:
        self.calls.append((messages, system))
        self.last_usage = Usage(input_tokens=5, output_tokens=len(self._response))
        for char in self._response:
            yield char
