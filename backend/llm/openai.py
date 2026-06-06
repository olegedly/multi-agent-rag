"""OpenAI chat-completions-format LLM client."""

import json
from typing import AsyncIterable

import httpx

from backend.llm.protocol import LLMClient, LLMError, LLMResponse, Message, Usage


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


class OpenAIClient(LLMClient):
    """LLM client for OpenAI-compatible endpoints (/v1/chat/completions)."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_tokens = max_tokens
        self._client = httpx.AsyncClient(timeout=timeout)

    async def generate(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        body = self._build_body(messages, system, stream=False)
        response = await self._client.post(
            f"{self.base_url}/chat/completions",
            json=body,
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise LLMError(
                status=response.status_code,
                message=_parse_error_body(await response.aread()),
            )

        data = response.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason")

        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        return LLMResponse(
            content=content or "",
            finish_reason=finish_reason,
            usage=usage,
        )

    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> AsyncIterable[str]:
        body = self._build_body(messages, system, stream=True)
        async with self._client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=body,
            headers=self._headers(),
        ) as response:
            if response.status_code >= 400:
                raise LLMError(
                    status=response.status_code,
                    message=_parse_error_body(await response.aread()),
                )
            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_block, buffer = buffer.split("\n\n", 1)
                    for delta in self._parse_sse_event(event_block):
                        yield delta
            if buffer.strip():
                for delta in self._parse_sse_event(buffer):
                    yield delta

    def _headers(self) -> dict:
        return {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }

    def _build_body(
        self,
        messages: list[Message],
        system: str | None,
        stream: bool,
    ) -> dict:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        for msg in messages:
            if msg.role != "system":
                msgs.append({"role": msg.role, "content": msg.content})
        return {
            "model": self.model,
            "messages": msgs,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

    @staticmethod
    def _parse_sse_event(event_block: str) -> list[str]:
        """Parse one SSE event block and return any text deltas."""
        deltas: list[str] = []
        data_line = ""

        for line in event_block.splitlines():
            line = line.strip()
            if line.startswith("data: "):
                data_line = line[6:]
            elif line == "data:":
                data_line = ""

        if not data_line or data_line == "[DONE]":
            return deltas

        try:
            payload = json.loads(data_line)
        except json.JSONDecodeError:
            return deltas

        for choice in payload.get("choices", []):
            delta = choice.get("delta", {})
            content = delta.get("content")
            if content:
                deltas.append(content)

        return deltas
