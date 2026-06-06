"""Fake LLM client and helpers for testing.

Mocks the LLMClient abstract interface so all business-logic tests
exercise the same seam that production code uses — no HTTP mocking
libraries needed outside the concrete client tests.
"""

from typing import AsyncIterable

from backend.llm.protocol import LLMClient, LLMResponse, Message, Usage


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
