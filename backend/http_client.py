"""Generic HTTP transport layer — shared by LLM and embedding clients.

Extracted from ``backend/llm/transport.py`` so neither domain module
owns the other's HTTP infrastructure.
"""

from __future__ import annotations

import json
from typing import AsyncIterable, Protocol, runtime_checkable

import httpx


# ── Exceptions ───────────────────────────────────────────────────────────────


class TransportError(Exception):
    """Raised by :class:`HttpTransport` on 4xx/5xx responses.

    Carries the HTTP status and a human-readable error message extracted
    from the response body.
    """

    def __init__(self, status: int, message: str, details: str | None = None):
        self.status = status
        self.details = details
        msg = f"HTTP error ({status}): {message}"
        if details:
            msg += f" — {details}"
        super().__init__(msg)


# ── Protocol ─────────────────────────────────────────────────────────────────


@runtime_checkable
class Transport(Protocol):
    """Protocol that both :class:`HttpTransport` and test fakes satisfy.

    ``send_stream`` is a plain ``def`` (not ``async def``) so the return
    type is ``AsyncIterable[str]`` instead of a coroutine — both async
    generators and coroutine-based streams satisfy it.
    """

    async def send(self, url: str, headers: dict, json_body: dict) -> httpx.Response:
        ...

    def send_stream(self, url: str, headers: dict, json_body: dict) -> AsyncIterable[str]:
        ...

    async def close(self) -> None:
        ...


# ── Error body parser ────────────────────────────────────────────────────────


def _parse_error_body(body: bytes) -> str:
    """Extract a human-readable error message from raw API response bytes."""
    try:
        data = json.loads(body)
        err = data.get("error", {})
        if isinstance(err, dict):
            return err.get("message", str(err))
        return str(err)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return body.decode("utf-8", errors="replace")[:500]


# ── Concrete transport ───────────────────────────────────────────────────────


class HttpTransport:
    """Owns an ``httpx.AsyncClient`` and provides ``send`` / ``send_stream``.

    Raises :class:`TransportError` on 4xx/5xx responses.  Streaming yields
    raw text chunks — SSE frame parsing is the caller's responsibility.
    """

    def __init__(self, timeout: float = 120.0):
        self._client = httpx.AsyncClient(timeout=timeout)

    async def send(
        self,
        url: str,
        headers: dict,
        json_body: dict,
    ) -> httpx.Response:
        """Non-streaming POST.

        Raises :class:`TransportError` on 4xx/5xx.
        """
        response = await self._client.post(url, json=json_body, headers=headers)
        if response.status_code >= 400:
            raise TransportError(
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
        """Streaming POST.  Yields raw response body text chunks.

        SSE framing is **not** parsed — callers handle boundary detection.
        Raises :class:`TransportError` on 4xx/5xx before yielding any data.
        """
        async with self._client.stream(
            "POST", url, json=json_body, headers=headers
        ) as response:
            if response.status_code >= 400:
                raise TransportError(
                    status=response.status_code,
                    message=_parse_error_body(await response.aread()),
                )
            async for chunk in response.aiter_text():
                yield chunk

    async def close(self) -> None:
        await self._client.aclose()
