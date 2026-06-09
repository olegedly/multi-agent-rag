"""Anthropic messages-format LLM client."""

import json
import json
from typing import AsyncIterable

from backend.llm.protocol import LLMClient, LLMResponse, Message, StreamEvent, ToolCall, ToolDef, Usage
from backend.llm.transport import HttpTransport, Transport


class AnthropicClient(LLMClient):
    """LLM client for Anthropic-compatible endpoints (e.g. DeepSeek via Anthropic format)."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        transport: Transport | None = None,
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
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> LLMResponse:
        body = self._build_body(messages, system, tools, stream=False)
        response = await self._transport.send(
            f"{self.base_url}/messages",
            headers=self._headers(),
            json_body=body,
        )

        data = response.json()
        content = ""
        tool_calls = None
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
            elif block.get("type") == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    args=block.get("input", {}),
                ))

        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
        )

        return LLMResponse(content=content, tool_calls=tool_calls, usage=usage)

    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> AsyncIterable[StreamEvent]:
        body = self._build_body(messages, system, tools, stream=True)
        buffer = ""
        async for chunk in self._transport.send_stream(
            f"{self.base_url}/messages",
            headers=self._headers(),
            json_body=body,
        ):
            buffer += chunk
            while "\n\n" in buffer:
                event_block, buffer = buffer.split("\n\n", 1)
                event = self._parse_sse_event(event_block)
                if event:
                    yield event
        if buffer.strip():
            event = self._parse_sse_event(buffer)
            if event:
                yield event

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
        tools: list[ToolDef] | None,
        stream: bool,
    ) -> dict:
        msgs: list[dict] = []
        for msg in messages:
            if msg.role == "system":
                continue
            entry: dict = {"role": msg.role}
            if msg.role == "assistant" and msg.tool_calls:
                # Anthropic format: tool_use content blocks
                content: list[dict] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]),
                    })
                entry["content"] = content
            elif msg.role == "tool" and msg.tool_call_id:
                entry["content"] = [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content,
                }]
            else:
                entry["content"] = msg.content
            msgs.append(entry)

        body: dict = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]
        return body

    @staticmethod
    def _parse_sse_event(event_block: str) -> StreamEvent | None:
        """Parse one SSE event block.

        Returns a StreamEvent or None if the event carries no actionable data.
        """
        data_line = ""

        for line in event_block.splitlines():
            line = line.strip()
            if line.startswith("data: "):
                data_line = line[6:]
            elif line == "data:":
                data_line = ""

        if not data_line or data_line == "[DONE]":
            return None

        try:
            event = json.loads(data_line)
        except json.JSONDecodeError:
            return None

        event_type = event.get("type")

        # Text content deltas
        if event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text:
                    return StreamEvent(content=text)
            return None

        # Message start — may contain initial content + tool_use blocks
        if event_type == "message_start":
            content = ""
            tool_calls = None
            msg = event.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    content += block["text"]
                elif block.get("type") == "tool_use":
                    if tool_calls is None:
                        tool_calls = []
                    tool_calls.append(ToolCall(
                        id=block["id"],
                        name=block["name"],
                        args=block.get("input", {}),
                    ))
            if content or tool_calls:
                return StreamEvent(content=content, tool_calls=tool_calls)
            return None

        # Message stop — carries final usage
        if event_type == "message_delta":
            raw_usage = event.get("usage", {})
            if raw_usage:
                usage = Usage(
                    input_tokens=raw_usage.get("input_tokens", 0),
                    output_tokens=raw_usage.get("output_tokens", 0),
                )
                return StreamEvent(usage=usage)
            return None

        # Content block start — might be a tool_use block starting
        if event_type == "content_block_start":
            block = event.get("content_block", {})
            if block.get("type") == "tool_use":
                tool_calls = [ToolCall(
                    id=block["id"],
                    name=block["name"],
                    args=block.get("input", {}),
                )]
                return StreamEvent(tool_calls=tool_calls)
            return None

        return None
