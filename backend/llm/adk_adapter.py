"""ADK BaseLlm adapter that delegates to any LLMClient implementation."""

from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from backend.llm.protocol import LLMClient, Message


def _to_protocol_messages(
    contents: list[types.Content],
) -> list[Message]:
    """Convert ADK Content list to our protocol Message list."""
    messages: list[Message] = []
    for content in contents:
        role = "assistant" if content.role in ("model", "assistant") else "user"
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
            messages.append(Message(role=role, content=text))
    return messages


def _extract_system(llm_request: LlmRequest) -> str | None:
    """Extract system instruction from an LlmRequest.

    Lives at llm_request.config.system_instruction and can be:
      - str
      - types.Content (extract text from its parts)
      - types.Part (use .text)
      - list[str | File | Part]
      - None
    """
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
    # Fallback for unexpected types
    return str(raw)


class AdkLlmAdapter(BaseLlm):
    """Wraps any LLMClient for use as an ADK model.

    Injects the concrete LLMClient via the constructor — no subclassing
    needed when switching providers.
    """

    def __init__(self, client: LLMClient):
        super().__init__(model=client.model)
        self._client = client

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        messages = _to_protocol_messages(llm_request.contents)
        system = _extract_system(llm_request)

        if stream:
            full_text = ""
            async for delta in self._client.generate_stream(messages, system=system):
                full_text += delta
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[types.Part(text=delta)],
                    ),
                    partial=True,
                )
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=full_text)],
                ),
                partial=False,
            )
        else:
            response = await self._client.generate(messages, system=system)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=response.content)],
                ),
                partial=False,
            )
