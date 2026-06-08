"""ADK BaseLlm adapter that delegates to any LLMClient implementation.

Now passes tool declarations through and emits ``function_call`` parts
when the LLM requests tool execution.
"""

from __future__ import annotations

from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from backend.llm.protocol import (
    LLMClient,
    Message,
    ToolCall,
    ToolDef,
    Usage,
)


def _to_protocol_messages(
    contents: list[types.Content],
) -> list[Message]:
    """Convert ADK Content list to our protocol Message list.

    ``function_call`` parts become assistant messages with the call
    serialised.  ``function_response`` parts become tool-role messages.
    """
    messages: list[Message] = []
    for content in contents:
        if content.role in ("model", "assistant"):
            text = ""
            for part in content.parts or []:
                if part.text:
                    text += part.text
                elif part.function_call:
                    import json

                    text += (
                        f"\n[function_call: "
                        f"{part.function_call.name}"
                        f"({json.dumps(part.function_call.args)})]"
                    )
                elif part.function_response:
                    import json

                    text += (
                        f"\n[function_result: "
                        f"{json.dumps(part.function_response.response)}]"
                    )
            if text:
                messages.append(Message(role="assistant", content=text))
        elif content.role == "tool":
            for part in content.parts or []:
                if part.function_response:
                    import json

                    text = json.dumps(part.function_response.response)
                    messages.append(Message(role="tool", content=text))
                elif part.text:
                    messages.append(Message(role="tool", content=part.text))
        else:
            for part in content.parts or []:
                if part.text:
                    messages.append(Message(role="user", content=part.text))
    return messages


def _extract_system(llm_request: LlmRequest) -> str | None:
    """Extract system instruction from an LlmRequest."""
    raw = llm_request.config.system_instruction
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, types.Part):
        return raw.text
    if isinstance(raw, types.Content):
        texts = [p.text for p in (raw.parts or []) if p.text]
        return "\n".join(texts) if texts else None
    if isinstance(raw, list):
        texts: list[str] = []
        for item in raw:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, types.Part) and item.text:
                texts.append(item.text)
        return "\n".join(texts) if texts else None
    return str(raw)


def _extract_tools(llm_request: LlmRequest) -> list[ToolDef] | None:
    """Extract tool declarations from an LlmRequest.

    ADK stores tools in ``llm_request.config.tools`` as a list of
    ``types.Tool``, each carrying ``function_declarations``.
    """
    raw_tools = getattr(llm_request.config, "tools", None)
    if not raw_tools:
        return None

    tool_defs: list[ToolDef] = []
    for tool in raw_tools:
        if isinstance(tool, types.Tool) and tool.function_declarations:
            for decl in tool.function_declarations:
                params = {}
                if decl.parameters and decl.parameters.properties:
                    params = _schema_to_dict(decl.parameters)
                elif decl.parameters_json_schema:
                    params = decl.parameters_json_schema
                tool_defs.append(
                    ToolDef(
                        name=decl.name or "",
                        description=decl.description or "",
                        parameters=params,
                    )
                )
    return tool_defs or None


def _tool_call_to_content(tc: ToolCall) -> types.Content:
    """Convert a protocol ToolCall to ADK Content with a function_call part."""
    return types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    id=tc.id,
                    name=tc.name,
                    args=tc.args,
                )
            )
        ],
    )


def _usage_to_adk(
    usage: Usage | None,
) -> types.GenerateContentResponseUsageMetadata | None:
    """Convert our Usage dataclass to ADK's usage metadata type."""
    if usage is None:
        return None
    return types.GenerateContentResponseUsageMetadata(
        prompt_token_count=usage.input_tokens,
        candidates_token_count=usage.output_tokens,
        total_token_count=usage.input_tokens + usage.output_tokens,
    )


def _schema_to_dict(schema: types.Schema) -> dict:
    """Recursively convert a types.Schema to a plain dict for JSON schema."""
    result: dict = {}
    if schema.type:
        raw = schema.type
        result["type"] = raw.value.lower() if hasattr(raw, "value") else str(raw).lower()
    if schema.description:
        result["description"] = schema.description
    if schema.properties:
        result["properties"] = {
            k: _schema_to_dict(v) for k, v in schema.properties.items()
        }
    if schema.required:
        result["required"] = list(schema.required)
    if schema.items:
        result["items"] = _schema_to_dict(schema.items)
    return result


class AdkLlmAdapter(BaseLlm):
    """Wraps any LLMClient for use as an ADK model.

    Injects the concrete LLMClient via the constructor — no subclassing
    needed when switching providers.

    After each successful generate the adapter fires
    ``client.usage_callback`` (if set) with the final ``Usage``.
    """

    def __init__(self, client: LLMClient):
        super().__init__(model=client.model)
        self._client = client

    async def _finalize_usage(
        self,
        usage: Usage | None,
    ) -> types.GenerateContentResponseUsageMetadata | None:
        """Fire the usage callback (if set) and return ADK usage metadata."""
        if usage is not None and self._client.usage_callback is not None:
            await self._client.usage_callback(usage)
        return _usage_to_adk(usage)

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        messages = _to_protocol_messages(llm_request.contents)
        system = _extract_system(llm_request)
        tools = _extract_tools(llm_request)

        if stream:
            async for event in self._client.generate_stream(
                messages,
                system=system,
                tools=tools,
            ):
                # Final event with usage → may carry tool_calls
                if event.usage is not None:
                    usage_adk = await self._finalize_usage(event.usage)

                    if event.tool_calls:
                        # Emit each tool call as a separate function_call content
                        for tc in event.tool_calls:
                            yield LlmResponse(
                                content=_tool_call_to_content(tc),
                                partial=False,
                                usage_metadata=usage_adk,
                            )
                    else:
                        yield LlmResponse(
                            content=types.Content(
                                role="model",
                                parts=[types.Part(text=event.content or "")],
                            ),
                            partial=False,
                            usage_metadata=usage_adk,
                        )
                    return

                # Intermediate text delta
                if event.content:
                    yield LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[types.Part(text=event.content)],
                        ),
                        partial=True,
                    )
        else:
            response = await self._client.generate(
                messages,
                system=system,
                tools=tools,
            )
            usage_adk = await self._finalize_usage(response.usage)

            if response.tool_calls:
                for tc in response.tool_calls:
                    yield LlmResponse(
                        content=_tool_call_to_content(tc),
                        partial=False,
                        usage_metadata=usage_adk,
                    )
            else:
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[types.Part(text=response.content)],
                    ),
                    partial=False,
                    usage_metadata=usage_adk,
                )
