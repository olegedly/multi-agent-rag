"""Tests for the ADK BaseLlm adapter.

Uses FakeLLMClient to verify the translation between ADK types and
the protocol Message / LLMResponse types without any HTTP calls.
"""

from google.adk.models.llm_request import LlmRequest
from google.genai import types

from backend.llm.adk_adapter import (
    AdkLlmAdapter,
    _extract_system,
    _to_protocol_messages,
)
from backend.llm.protocol import Message, Usage
from tests.fakes import CollectingLLMClient, FakeLLMClient


class FireCallbackLLMClient(FakeLLMClient):
    """FakeLLMClient that carries a usage_callback for testing."""

    def __init__(self, responses: list[str] | None = None):
        super().__init__(responses)
        self.usage_callback = None


# ── Helper to build an LlmRequest ────────────────────────────────────────────


def _make_request(
    texts: list[str],
    roles: list[str] | None = None,
    system: str | None = None,
) -> LlmRequest:
    """Build a minimal LlmRequest with the given text parts."""
    if roles is None:
        roles = ["user"] * len(texts)

    contents = [
        types.Content(role=role, parts=[types.Part(text=text)])
        for text, role in zip(texts, roles)
    ]

    config = types.GenerateContentConfig()
    if system is not None:
        config.system_instruction = system

    return LlmRequest(contents=contents, config=config)


# ── Utility tests ────────────────────────────────────────────────────────────


class TestToProtocolMessages:
    def test_converts_user_content(self) -> None:
        contents = [types.Content(role="user", parts=[types.Part(text="hello")])]
        messages = _to_protocol_messages(contents)
        assert len(messages) == 1
        assert messages[0] == Message(role="user", content="hello")

    def test_converts_model_content(self) -> None:
        """ADK uses 'model' role for assistant turns."""
        contents = [types.Content(role="model", parts=[types.Part(text="hi there")])]
        messages = _to_protocol_messages(contents)
        assert messages[0] == Message(role="assistant", content="hi there")

    def test_converts_mixed_roles(self) -> None:
        contents = [
            types.Content(role="user", parts=[types.Part(text="q1")]),
            types.Content(role="model", parts=[types.Part(text="a1")]),
            types.Content(role="user", parts=[types.Part(text="q2")]),
        ]
        messages = _to_protocol_messages(contents)
        assert [m.role for m in messages] == ["user", "assistant", "user"]

    def test_converts_function_call_part(self) -> None:
        fn = types.FunctionCall(name="search", args={"q": "test"})
        contents = [types.Content(role="model", parts=[types.Part(function_call=fn)])]
        messages = _to_protocol_messages(contents)
        assert len(messages) == 1
        assert '[function_call: search({"q": "test"})]' in messages[0].content

    def test_converts_function_response_part(self) -> None:
        fn_resp = types.FunctionResponse(name="search", response={"result": "data"})
        contents = [
            types.Content(role="model", parts=[types.Part(function_response=fn_resp)])
        ]
        messages = _to_protocol_messages(contents)
        assert '[function_result: {"result": "data"}]' in messages[0].content

    def test_skips_empty_parts(self) -> None:
        contents = [types.Content(role="user", parts=[])]
        messages = _to_protocol_messages(contents)
        assert len(messages) == 0

    def test_skips_none_parts(self) -> None:
        contents = [types.Content(role="user", parts=[types.Part()])]
        messages = _to_protocol_messages(contents)
        assert len(messages) == 0


class TestExtractSystem:
    def test_returns_none_when_no_system(self) -> None:
        request = _make_request(["hi"])
        assert _extract_system(request) is None

    def test_extracts_string_system(self) -> None:
        request = _make_request(["hi"], system="be helpful")
        assert _extract_system(request) == "be helpful"

    def test_extracts_from_content(self) -> None:
        config = types.GenerateContentConfig(
            system_instruction=types.Content(parts=[types.Part(text="from content")])
        )
        contents = [types.Content(role="user", parts=[types.Part(text="hi")])]
        request = LlmRequest(contents=contents, config=config)
        assert _extract_system(request) == "from content"

    def test_extracts_from_part(self) -> None:
        config = types.GenerateContentConfig(
            system_instruction=types.Part(text="from part")
        )
        contents = [types.Content(role="user", parts=[types.Part(text="hi")])]
        request = LlmRequest(contents=contents, config=config)
        assert _extract_system(request) == "from part"

    def test_extracts_from_list_of_strings(self) -> None:
        config = types.GenerateContentConfig(system_instruction=["first", " second"])
        contents = [types.Content(role="user", parts=[types.Part(text="hi")])]
        request = LlmRequest(contents=contents, config=config)
        assert _extract_system(request) == "first\n second"


# ── Usage callback seam ────────────────────────────────────────────────────


class TestUsageCallback:
    """The optional usage_callback fires with the accumulated Usage after
    each generate completes. This is the seam for the daily token budget."""

    async def test_fires_after_streaming(self) -> None:
        client = FireCallbackLLMClient(responses=["abc"])
        recorded = []

        async def cb(usage: Usage) -> None:
            recorded.append(usage)

        client.usage_callback = cb
        adapter = AdkLlmAdapter(client)

        request = _make_request(["hi"])
        async for _ in adapter.generate_content_async(request, stream=True):
            pass

        assert len(recorded) == 1
        assert recorded[0].input_tokens == 10
        assert recorded[0].output_tokens == 3  # len("abc")

    async def test_does_not_fire_when_not_set(self) -> None:
        client = FireCallbackLLMClient(responses=["abc"])
        adapter = AdkLlmAdapter(client)
        request = _make_request(["hi"])
        # Should not raise
        async for _ in adapter.generate_content_async(request, stream=True):
            pass

    async def test_fires_after_non_streaming(self) -> None:
        client = FireCallbackLLMClient(responses=["xyz"])
        recorded = []

        async def cb(usage: Usage) -> None:
            recorded.append(usage)

        client.usage_callback = cb
        adapter = AdkLlmAdapter(client)

        request = _make_request(["hi"])
        async for _ in adapter.generate_content_async(request, stream=False):
            pass

        assert len(recorded) == 1
        assert recorded[0].output_tokens == 3  # len("xyz")


# ── Adapter tests ────────────────────────────────────────────────────────────


class TestAdkLlmAdapter:
    async def test_non_streaming_returns_full_content(self) -> None:
        fake = FakeLLMClient(responses=["Hello world"])
        adapter = AdkLlmAdapter(fake)

        request = _make_request(["hi"])
        responses = []
        async for response in adapter.generate_content_async(request, stream=False):
            responses.append(response)

        assert len(responses) == 1
        final = responses[0]
        assert final.content is not None
        assert final.content.parts is not None
        assert final.content.parts[0].text == "Hello world"
        assert final.partial is False

    async def test_non_streaming_carries_usage(self) -> None:
        fake = FakeLLMClient(responses=["hi"])
        adapter = AdkLlmAdapter(fake)

        request = _make_request(["hi"])
        async for response in adapter.generate_content_async(request, stream=False):
            assert response.usage_metadata is not None
            assert response.usage_metadata.prompt_token_count == 10
            assert response.usage_metadata.candidates_token_count == 2  # len("hi")

    async def test_streaming_yields_deltas_then_final(self) -> None:
        fake = FakeLLMClient(responses=["ab"])
        adapter = AdkLlmAdapter(fake)

        request = _make_request(["hi"])
        parts: list[str] = []
        final_partial = None
        async for response in adapter.generate_content_async(request, stream=True):
            content = response.content
            text = content.parts[0].text if content is not None and content.parts else ""
            if text:
                parts.append(text)
            if not response.partial:
                final_partial = response.partial

        # ADK yields individual deltas (a, b) then a final re-accumulated chunk (ab)
        assert parts == ["a", "b", "ab"]
        assert final_partial is False

    async def test_streaming_final_has_usage(self) -> None:
        fake = FakeLLMClient(responses=["ab"])
        adapter = AdkLlmAdapter(fake)

        request = _make_request(["hi"])
        final_usage = None
        async for response in adapter.generate_content_async(request, stream=True):
            if not response.partial:
                final_usage = response.usage_metadata

        assert final_usage is not None
        assert final_usage.prompt_token_count == 10

    async def test_passes_system_instruction(self) -> None:
        collecting = CollectingLLMClient(response="answer")
        adapter = AdkLlmAdapter(collecting)

        request = _make_request(["hi"], system="be concise")
        async for _ in adapter.generate_content_async(request, stream=False):
            pass

        assert len(collecting.calls) == 1
        _, system = collecting.calls[0]
        assert system == "be concise"

    async def test_passes_messages(self) -> None:
        collecting = CollectingLLMClient(response="answer")
        adapter = AdkLlmAdapter(collecting)

        request = _make_request(["hello", "world"], roles=["user", "assistant"])
        async for _ in adapter.generate_content_async(request, stream=False):
            pass

        assert len(collecting.calls) == 1
        messages, _ = collecting.calls[0]
        assert len(messages) == 2
        assert messages[0].content == "hello"
        assert messages[1].content == "world"
