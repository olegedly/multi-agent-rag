"""Abstract LLM client interface — the dependency inversion boundary."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import AsyncIterable


@dataclass
class Message:
    """A single message in a conversation.

    For assistant messages with tool calls, *tool_calls* carries the
    opaque provider-format dicts (e.g. OpenAI ``{id, type, function}``
    shape).  For tool-role messages, *tool_call_id* links back to the
    call that produced the result.
    """

    role: str  # "user" | "assistant" | "system" | "tool"
    content: str

    # Assistant messages only: list of tool call dicts in the provider's
    # wire format (e.g. OpenAI ``{"id": ..., "type": "function",
    # "function": {"name": ..., "arguments": ...}}``).
    tool_calls: list[dict] | None = None

    # Tool-role messages only: the ``id`` of the tool call whose result
    # this message carries.
    tool_call_id: str | None = None


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
class ToolDef:
    """A tool definition to advertise to the LLM."""

    name: str
    description: str
    parameters: dict  # JSON schema dict


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""

    id: str
    name: str
    args: dict


@dataclass
class StreamEvent:
    """A single event yielded during streaming generation.

    Most events carry ``content`` (text delta) and no ``tool_calls``.
    The final event carries accumulated ``usage`` and, if the model
    requested tool calls, the complete ``tool_calls`` list.
    """

    content: str = ""
    tool_calls: list[ToolCall] | None = None
    usage: Usage | None = None


@dataclass
class LLMResponse:
    """A complete (non-streaming) response from the LLM."""

    content: str
    tool_calls: list[ToolCall] | None = None
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
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Non-streaming generation. Returns the complete response."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> AsyncIterable[StreamEvent]:
        """Streaming generation. Yields ``StreamEvent`` tuples.

        Most events carry ``content`` (text delta). The final event
        carries accumulated ``usage`` and, if applicable, ``tool_calls``.
        """
        ...
        if False:  # pragma: no cover — make the generator type-check
            yield StreamEvent()
