"""Anthropic messages-format LLM client."""

import json
from typing import AsyncIterable

from backend.llm.protocol import LLMClient, LLMResponse, Message, Usage
from backend.llm.transport import HttpTransport


class AnthropicClient(LLMClient):
    """LLM client for Anthropic-compatible endpoints (e.g. DeepSeek via Anthropic format)."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        transport: HttpTransport | None = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_tokens = max_tokens
        self._transport = transport or HttpTransport(timeout=timeout)

    async def generate(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        body = self._build_body(messages, system, stream=False)
        response = await self._transport.send(
            f"{self.base_url}/messages",
            headers=self._headers(),
            json_body=body,
        )

        data = response.json()
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
        )

        return LLMResponse(content=content, usage=usage)

    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> AsyncIterable[tuple[str, Usage | None]]:
        body = self._build_body(messages, system, stream=True)
        buffer = ""
        async for chunk in self._transport.send_stream(
            f"{self.base_url}/messages",
            headers=self._headers(),
            json_body=body,
        ):
            buffer += chunk
            while "\n\n" in buffer:
                event_block, buffer = buffer.split("\n\n", 1)
                deltas, usage = self._parse_sse_event(event_block)
                for delta in deltas:
                    yield delta, usage
                if not deltas and usage is not None:
                    yield "", usage
        if buffer.strip():
            deltas, usage = self._parse_sse_event(buffer)
            for delta in deltas:
                yield delta, usage

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _build_body(
        self,
        messages: list[Message],
        system: str | None,
        stream: bool,
    ) -> dict:
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in messages
                if msg.role != "system"
            ],
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        if system:
            body["system"] = system
        return body

    @staticmethod
    def _parse_sse_event(
        event_block: str,
    ) -> tuple[list[str], Usage | None]:
        """Parse one SSE event block.

        Returns (text_deltas, usage) — usage is populated from the final
        message_stop event that carries token counts.
        """
        deltas: list[str] = []
        usage: Usage | None = None
        data_line = ""

        for line in event_block.splitlines():
            line = line.strip()
            if line.startswith("data: "):
                data_line = line[6:]
            elif line == "data:":
                data_line = ""

        if not data_line or data_line == "[DONE]":
            return deltas, usage

        try:
            event = json.loads(data_line)
        except json.JSONDecodeError:
            return deltas, usage

        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text:
                    deltas.append(text)
        elif event.get("type") == "message_start":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    deltas.append(block["text"])
        elif event.get("type") == "message_delta":
            raw_usage = event.get("usage", {})
            if raw_usage:
                usage = Usage(
                    input_tokens=raw_usage.get("input_tokens", 0),
                    output_tokens=raw_usage.get("output_tokens", 0),
                )

        return deltas, usage
