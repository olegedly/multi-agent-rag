"""HTTP transport layer for LLM API calls.

Extracts HTTP client lifecycle and error handling into a reusable
class so that each LLM client implementation (OpenAI, Anthropic, etc.)
can focus on protocol-specific request/response parsing.
"""

import json
from typing import AsyncIterable, Protocol, runtime_checkable

import httpx

from backend.llm.protocol import LLMError


@runtime_checkable
class Transport(Protocol):
    """Protocol that both ``HttpTransport`` and ``FakeTransport`` satisfy."""

    async def send(self, url: str, headers: dict, json_body: dict) -> httpx.Response:
        ...

    async def send_stream(self, url: str, headers: dict, json_body: dict) -> AsyncIterable[str]:
        ...

    async def close(self) -> None:
        ...


def _parse_error_body(body: bytes) -> str:
    """Extract a user-facing error message from raw API response bytes."""
    try:
        data = json.loads(body)
        err = data.get("error", {})
        if isinstance(err, dict):
            return err.get("message", str(err))
        return str(err)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return body.decode("utf-8", errors="replace")[:500]


class HttpTransport:
    """Owns an ``httpx.AsyncClient`` and provides ``send`` / ``send_stream``.

    Wraps HTTP errors into :class:`LLMError`. Streaming yields raw text chunks
    — SSE frame parsing is the caller's responsibility.
    """

    def __init__(self, timeout: float = 120.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    async def send(
        self,
        url: str,
        headers: dict,
        json_body: dict,
    ) -> httpx.Response:
        """Non-streaming POST. Raises :class:`LLMError` on 4xx/5xx."""
        response = await self._client.post(url, json=json_body, headers=headers)
        if response.status_code >= 400:
            raise LLMError(
                status=response.status_code,
                message=_parse_error_body(await response.aread()),
            )
        return response

    async def send_stream(
        self,
        url: str,
        headers: dict,
        json_body: dict,
    ) -> AsyncIterable[str]:
        """Streaming POST. Yields response body text chunks.

        Raises :class:`LLMError` on 4xx/5xx before yielding any data.
        SSE framing is **not** parsed — callers handle ``\\n\\n`` boundaries.
        """
        async with self._client.stream(
            "POST", url, json=json_body, headers=headers
        ) as response:
            if response.status_code >= 400:
                raise LLMError(
                    status=response.status_code,
                    message=_parse_error_body(await response.aread()),
                )
            async for chunk in response.aiter_text():
                yield chunk

    async def close(self) -> None:
        await self._client.aclose()
