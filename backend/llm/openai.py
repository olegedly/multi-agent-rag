"""OpenAI chat-completions-format LLM client."""

import json
from typing import AsyncIterable

from backend.llm.protocol import LLMClient, LLMResponse, Message, Usage
from backend.llm.transport import HttpTransport


class OpenAIClient(LLMClient):
    """LLM client for OpenAI-compatible endpoints (/v1/chat/completions)."""

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
        self.last_usage: Usage | None = None

    async def generate(
        self,
        messages: list[Message],
        system: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        body = self._build_body(messages, system, stream=False)
        response = await self._transport.send(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json_body=body,
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
        buffer = ""
        async for chunk in self._transport.send_stream(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json_body=body,
        ):
            buffer += chunk
            while "\n\n" in buffer:
                event_block, buffer = buffer.split("\n\n", 1)
                deltas, usage = self._parse_sse_event(event_block)
                if usage:
                    self.last_usage = usage
                for delta in deltas:
                    yield delta
        if buffer.strip():
            deltas, usage = self._parse_sse_event(buffer)
            if usage:
                self.last_usage = usage
            for delta in deltas:
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
    def _parse_sse_event(
        event_block: str,
    ) -> tuple[list[str], Usage | None]:
        """Parse one SSE event block.

        Returns (text_deltas, usage) — usage is populated from the final
        streaming event that carries token counts.
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
            payload = json.loads(data_line)
        except json.JSONDecodeError:
            return deltas, usage

        for choice in payload.get("choices", []):
            delta = choice.get("delta", {})
            content = delta.get("content")
            if content:
                deltas.append(content)

        # The final streaming event carries usage metadata
        raw_usage = payload.get("usage")
        if raw_usage:
            usage = Usage(
                input_tokens=raw_usage.get("prompt_tokens", 0),
                output_tokens=raw_usage.get("completion_tokens", 0),
            )

        return deltas, usage
