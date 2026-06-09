"""OpenAI chat-completions-format LLM client."""

import json
from typing import AsyncIterable

from backend.llm.protocol import LLMClient, LLMResponse, Message, StreamEvent, ToolCall, ToolDef, Usage
from backend.llm.transport import HttpTransport, Transport


class OpenAIClient(LLMClient):
    """LLM client for OpenAI-compatible endpoints (/v1/chat/completions)."""

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

    # ── Non-streaming ────────────────────────────────────────────────────────

    async def generate(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> LLMResponse:
        body = self._build_body(messages, system, tools, stream=False)
        response = await self._transport.send(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json_body=body,
        )

        data = response.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "")
        finish_reason = choice.get("finish_reason")

        tool_calls = _parse_tool_calls_from_message(msg)

        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        return LLMResponse(
            content=content or "",
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    # ── Streaming ────────────────────────────────────────────────────────────

    async def generate_stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        **kwargs,
    ) -> AsyncIterable[StreamEvent]:
        body = self._build_body(messages, system, tools, stream=True)
        buffer = ""

        # Accumulate streaming tool call deltas by index:
        #   {index: {"id": ..., "name": ..., "args": "accumulated_string"}}
        _tc_deltas: dict[int, dict] = {}

        async for chunk in self._transport.send_stream(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json_body=body,
        ):
            buffer += chunk
            while "\n\n" in buffer:
                event_block, buffer = buffer.split("\n\n", 1)
                for ev in self._iter_stream_events(event_block, _tc_deltas):
                    if ev is not None:
                        yield ev

        if buffer.strip():
            for ev in self._iter_stream_events(buffer, _tc_deltas):
                if ev is not None:
                    yield ev

        # Flush any remaining accumulated tool calls (defensive)
        tcs = _finalize_deltas(_tc_deltas)
        if tcs:
            yield StreamEvent(tool_calls=tcs)

    # ── Internals ───────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "authorization": f"Bearer {self.api_key}",
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
        if system:
            msgs.append({"role": "system", "content": system})
        for msg in messages:
            if msg.role != "system":
                entry: dict = {"role": msg.role, "content": msg.content}
                if msg.tool_calls:
                    entry["tool_calls"] = msg.tool_calls
                if msg.tool_call_id:
                    entry["tool_call_id"] = msg.tool_call_id
                msgs.append(entry)
        body: dict = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        return body

    @staticmethod
    def _parse_sse_event(event_block: str) -> StreamEvent | None:
        """Parse a single SSE event block (no tool-call accumulation).

        Convenience wrapper around ``_iter_stream_events`` for test use.
        """
        tc_deltas: dict[int, dict] = {}
        for ev in OpenAIClient._iter_stream_events(event_block, tc_deltas):
            return ev
        return None

    @staticmethod
    def _iter_stream_events(
        event_block: str,
        tc_deltas: dict[int, dict],
    ):
        """Parse a single SSE block, update tc_deltas, yield StreamEvents."""
        data_line = ""
        for line in event_block.splitlines():
            line = line.strip()
            if line.startswith("data: "):
                data_line = line[6:]
            elif line.startswith("data:"):
                data_line = line[5:]

        if not data_line or data_line == "[DONE]":
            return

        try:
            payload = json.loads(data_line)
        except json.JSONDecodeError:
            return

        content = ""
        usage = None

        for choice in payload.get("choices", []):
            delta = choice.get("delta", {})
            text = delta.get("content")
            if text:
                content += text

            # Accumulate streaming tool call deltas
            raw_tcs = delta.get("tool_calls")
            if raw_tcs:
                for raw_tc in raw_tcs:
                    idx = raw_tc.get("index", 0)
                    bucket = tc_deltas.setdefault(idx, {"id": "", "name": "", "args": ""})
                    tc_id = raw_tc.get("id", "")
                    if tc_id:
                        bucket["id"] = tc_id
                    fn = raw_tc.get("function", {})
                    fn_name = fn.get("name", "")
                    if fn_name:
                        bucket["name"] = fn_name
                    fn_args = fn.get("arguments", "")
                    if fn_args:
                        bucket["args"] += fn_args

        # Final streaming event carries usage + completes tool calls
        raw_usage = payload.get("usage")
        if raw_usage:
            usage = Usage(
                input_tokens=raw_usage.get("prompt_tokens", 0),
                output_tokens=raw_usage.get("completion_tokens", 0),
            )
            tcs = _finalize_deltas(tc_deltas)
            yield StreamEvent(content=content, tool_calls=tcs, usage=usage)
        elif content:
            yield StreamEvent(content=content)


def _parse_tool_calls_from_message(msg: dict) -> list[ToolCall] | None:
    """Parse tool_calls from a non-streaming response message dict."""
    raw_tool_calls = msg.get("tool_calls")
    if not raw_tool_calls:
        return None
    return [
        ToolCall(
            id=tc["id"],
            name=tc["function"]["name"],
            args=json.loads(tc["function"]["arguments"]),
        )
        for tc in raw_tool_calls
    ]


def _finalize_deltas(tc_deltas: dict[int, dict]) -> list[ToolCall] | None:
    """Convert accumulated streaming deltas into completed ToolCall objects."""
    if not tc_deltas:
        return None
    result = []
    for idx in sorted(tc_deltas.keys()):
        bucket = tc_deltas[idx]
        args = json.loads(bucket["args"]) if bucket["args"] else {}
        result.append(ToolCall(id=bucket["id"], name=bucket["name"], args=args))
    tc_deltas.clear()
    return result
