"""Abstract LLM client interface — the dependency inversion boundary."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import AsyncIterable


@dataclass
class Message:
    """A single message in a conversation."""

    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class Usage:
    """Token usage information."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMError(Exception):
    """Raised when the LLM API returns an error response.

    Carries the HTTP status and the API's error message so it can
    be surfaced through ADK's RUN_ERROR event to the frontend.
    """

    def __init__(self, status: int, message: str, details: str | None = None):
        self.status = status
        self.details = details
        msg = f"LLM API error ({status}): {message}"
        if details:
            msg += f" — {details}"
        super().__init__(msg)


@dataclass
class LLMResponse:
    """A complete (non-streaming) response from the LLM."""

    content: str
    finish_reason: str | None = None
    usage: Usage | None = None


class LLMClient(ABC):
    """Abstract LLM client.

    Every provider implementation (Anthropic, OpenAI, etc.) implements this
    interface. The ADK adapter layer translates between ADK's types and
    these pure-python types.

    ``usage_callback`` is an optional hook called after each successful
    generate with the final ``Usage``. It is the seam for the daily
    demo token budget — the adapter layer fires it, the app wires a
    closure that increments the budget file.
    """

    model: str
    usage_callback: Callable[[Usage], Awaitable[None]] | None = None

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Non-streaming generation. Returns the complete response."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> AsyncIterable[tuple[str, Usage | None]]:
        """Streaming generation. Yields ``(text_delta, usage)`` tuples.

        Most yields carry ``usage=None`` — the final chunk is guaranteed
        to carry the accumulated ``Usage`` when the API provides it.
        """
        ...
        if False:  # pragma: no cover — make the generator type-check
            yield "", None
