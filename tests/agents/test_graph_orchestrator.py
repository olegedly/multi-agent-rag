"""Tests for graph_orchestrator — multi-agent LangGraph pipeline.

Exercises ``run_orchestrator()`` with a mocked model to verify
state transitions, event shape with agent names, interleaved
reasoning + tool calls, and correct multi-agent orchestration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from ag_ui.core.events import (
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageStartEvent,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk

from backend.corpus_config import CorporaConfig


@pytest.fixture
def corpora_config():
    return CorporaConfig.from_dicts(
        [
            {
                "id": "corpus-a-uuid",
                "slug": "eu-ai-act",
                "name": "EU AI Act",
                "description": "Test corpus",
                "chunker": "markdown-heading",
                "documents": "corpora/eu-ai-act/**/*.md",
            },
        ]
    )


def _make_async_gen(values):
    """Turn a list of values into an async generator."""

    async def _gen(*args, **kwargs):
        for v in values:
            yield v

    return _gen


# ── Tracer bullet 1: basic orchestration with three agents ──────────────────


@pytest.fixture
def mock_basic_orchestration():
    """Set up mock_model.astream / ainvoke for three agent calls.

    Each agent's astream yields AIMessageChunks and ainvoke returns
    an AIMessage.  An internal call counter cycles through the three
    agents using message history length as signal.
    """
    astream_call_count: list[int] = [0]
    agents = [
        (["Researcher findings here"], "Researcher findings here"),
        (["Critic ", "feedback"], "Critic feedback"),
        (["Synthesized answer"], "Synthesized answer"),
    ]

    async def _astream_impl(messages, **kwargs):
        idx = astream_call_count[0]
        astream_call_count[0] += 1
        chunks, _ = agents[idx % len(agents)]
        for part in chunks:
            yield AIMessageChunk(content=part)

    async def _ainvoke_impl(messages):
        # ainvoke is no longer called by the orchestrator but kept for
        # backward compatibility in tests that rely on it directly.
        return AIMessage(content="")

    def _apply(model: AsyncMock):
        model.astream = _astream_impl
        model.ainvoke = _ainvoke_impl
        model.bind_tools = lambda _tools: model
        # bind_tools must return the model itself so the explicit agent
        # loop can call model.astream / model.ainvoke on the result.
        model.bind_tools = lambda tools: model

    yield _apply


@pytest.fixture
def mock_model():
    """A fake BaseChatModel that sidesteps real API credentials."""
    m = AsyncMock(spec=BaseChatModel)
    m.bind_tools = lambda tools: m
    return m


class TestBasicOrchestration:
    """run_orchestrator() yields correct events for three-agent flow."""

    async def test_emits_run_started_first(
        self,
        corpora_config,
        mock_basic_orchestration,
        mock_model,
    ):
        """First event must be RunStartedEvent."""
        mock_basic_orchestration(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
        )
        assert len(events) >= 1
        assert isinstance(events[0], RunStartedEvent)

    async def test_emits_three_text_blocks(
        self,
        corpora_config,
        mock_basic_orchestration,
        mock_model,
    ):
        """Three TEXT_MESSAGE_START events appear — one per agent."""
        mock_basic_orchestration(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
        )
        starts = [e for e in events if isinstance(e, TextMessageStartEvent)]
        assert len(starts) == 3

    async def test_agent_names_on_text_starts(
        self,
        corpora_config,
        mock_basic_orchestration,
        mock_model,
    ):
        """Each TEXT_MESSAGE_START has the correct agent name."""
        mock_basic_orchestration(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
        )
        starts = [e for e in events if isinstance(e, TextMessageStartEvent)]
        names = [s.name for s in starts]
        assert names == ["Researcher", "Critic", "Synthesizer"]

    async def test_emits_run_finished_last(
        self,
        corpora_config,
        mock_basic_orchestration,
        mock_model,
    ):
        """Last event must be a single RunFinishedEvent."""
        mock_basic_orchestration(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
        )
        finished = [e for e in events if isinstance(e, RunFinishedEvent)]
        assert len(finished) == 1
        assert events[-1] is finished[0]

    async def test_single_run_started(
        self,
        corpora_config,
        mock_basic_orchestration,
        mock_model,
    ):
        """Only one RUN_STARTED event in the entire stream."""
        mock_basic_orchestration(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
        )
        starts = [e for e in events if isinstance(e, RunStartedEvent)]
        assert len(starts) == 1

    async def test_accrued_content_across_agents(
        self,
        corpora_config,
        mock_basic_orchestration,
        mock_model,
    ):
        """All three agents' text content appears in the event stream."""
        mock_basic_orchestration(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
        )
        content_parts = [
            e.delta for e in events if isinstance(e, TextMessageContentEvent)
        ]
        combined = "".join(content_parts)
        assert "Researcher findings here" in combined
        assert "Critic feedback" in combined
        assert "Synthesized answer" in combined


# ── Tracer bullet 2: error handling ────────────────────────────────────────


@pytest.fixture
def mock_first_agent_crash():
    """Mock model so the first agent crashes mid-stream."""
    call_count: list[int] = [0]

    async def _astream_impl(messages, **kwargs):
        idx = call_count[0]
        # First call: yield a chunk, then raise
        if idx == 0:
            yield AIMessageChunk(content="Before crash")
            raise RuntimeError("API failure")
        yield AIMessageChunk(content="Should not reach")

    async def _ainvoke_impl(messages):
        idx = call_count[0]
        if idx == 0:
            call_count[0] += 1
            return AIMessage(content="Before crash")
        return AIMessage(content="Should not reach")

    def _apply(model: AsyncMock):
        model.astream = _astream_impl
        model.ainvoke = _ainvoke_impl
        model.bind_tools = lambda _tools: model

    yield _apply


class TestOrchestratorErrors:
    """run_orchestrator() handles agent errors gracefully."""

    async def test_emits_run_error_on_crash(
        self,
        corpora_config,
        mock_first_agent_crash,
        mock_model,
    ):
        """When agent crashes, orchestrator yields RUN_ERROR."""
        mock_first_agent_crash(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
        )
        errors = [e for e in events if isinstance(e, RunErrorEvent)]
        assert len(errors) == 1

    async def test_no_run_finished_after_crash(
        self,
        corpora_config,
        mock_first_agent_crash,
        mock_model,
    ):
        """When agent crashes, no RUN_FINISHED event."""
        mock_first_agent_crash(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
        )
        finished = [e for e in events if isinstance(e, RunFinishedEvent)]
        assert len(finished) == 0


# ── Tracer bullet 3: interleaved reasoning + tool calls ────────────────────


@pytest.fixture
def mock_interleaved_agent():
    """Mock model for interleaved reasoning + tool calls across 3 agents.

    Agent 1 and Agent 2 each do tool-call then text (2 iterations).
    Agent 3 does only text (1 iteration).
    Uses astream call counter (self-contained, no ainvoke dependency).
    """
    astream_count: list[int] = [0]

    async def _astream_impl(messages, **kwargs):
        idx = astream_count[0]
        astream_count[0] += 1
        # Even indices below 4 = first call for Agent 1 (idx=0) / Agent 2 (idx=2)
        if idx % 2 == 0 and idx < 4:
            tid = "call-1" if idx == 0 else "call-2"
            yield AIMessageChunk(
                content="",
                additional_kwargs={"reasoning_content": f"Thought {idx + 1}"},
            )
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "id": tid,
                        "name": "rag_search",
                        "args": '{"query":"test"}',
                        "index": 0,
                    }
                ],
            )
        else:
            # Second calls (text) for Agent 1/2, all calls for Agent 3
            yield AIMessageChunk(content="Final answer")

    async def _ainvoke_impl(messages):
        return AIMessage(content="")

    def _apply(model: AsyncMock):
        model.astream = _astream_impl
        model.ainvoke = _ainvoke_impl
        model.bind_tools = lambda _tools: model

    yield _apply


class TestInterleavedReasoningTools:
    """Agent nodes with multiple reasoning blocks between tool calls."""

    async def test_emits_two_thinking_blocks(
        self,
        corpora_config,
        mock_interleaved_agent,
        mock_model,
    ):
        """Two STEP_STARTED events appear for two reasoning blocks."""
        mock_interleaved_agent(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
            slug="eu-ai-act",
        )

        step_starts = [e for e in events if isinstance(e, StepStartedEvent)]
        assert len(step_starts) == 2, (
            f"Expected 2 STEP_STARTED for two reasoning blocks, got {len(step_starts)}"
        )

    async def test_thinking_and_tool_interleave_ordering(
        self,
        corpora_config,
        mock_interleaved_agent,
        mock_model,
    ):
        """Events appear in correct interleaved order."""
        mock_interleaved_agent(mock_model)
        events = await _collect_orchestrator_events(
            corpora_config,
            model=mock_model,
            slug="eu-ai-act",
        )

        types = [type(e).__name__ for e in events]

        # The first agent should produce:
        #   TextMessageStartEvent
        #   StepStartedEvent  (1st reasoning)
        #   ReasoningMessageStartEvent
        #   ReasoningMessageContentEvent
        #   ToolCallStartEvent(call-1)
        #   ToolCallArgsEvent(call-1)
        #   ReasoningMessageEndEvent  (closed by tool result)
        #   ToolCallEndEvent(call-1)
        #   ToolCallResultEvent(call-1)
        #   StepStartedEvent  (2nd reasoning, new stepId)
        #   ReasoningMessageStartEvent
        #   ReasoningMessageContentEvent
        #   ToolCallStartEvent(call-2)
        #   ToolCallArgsEvent(call-2)
        #   ReasoningMessageEndEvent  (closed by tool result)
        #   ToolCallEndEvent(call-2)
        #   ToolCallResultEvent(call-2)
        #   TextMessageContentEvent("Final answer")
        #   TextMessageEndEvent

        step_idx = [i for i, t in enumerate(types) if t == "StepStartedEvent"]
        assert len(step_idx) == 2, "Need exactly two StepStartedEvent"

        reasoning_end_idx = [
            i for i, t in enumerate(types) if t == "ReasoningMessageEndEvent"
        ]
        assert len(reasoning_end_idx) == 2, "Need exactly two ReasoningMessageEndEvent"

        # First reasoning block: StepStartedEvent before first ReasoningMessageEndEvent
        assert step_idx[0] < reasoning_end_idx[0], (
            "First STEP_STARTED must be before first REASONING_MESSAGE_END"
        )

        # Tool calls between the two reasoning blocks
        # call-1 must be between step_idx[0] and reasoning_end_idx[0]
        call1_start = next(i for i, t in enumerate(types) if t == "ToolCallStartEvent")
        assert step_idx[0] < call1_start < reasoning_end_idx[0], (
            "Tool call 1 must be between STEP_STARTED and REASONING_MESSAGE_END"
        )

        # Second reasoning block starts after first tool result
        # StepStartedEvent must be after first ReasoningMessageEndEvent
        assert reasoning_end_idx[0] < step_idx[1], (
            "Second STEP_STARTED must be after first REASONING_MESSAGE_END"
        )

        # Second tool call must be between second step and second reasoning end
        call_starts = [i for i, t in enumerate(types) if t == "ToolCallStartEvent"]
        assert len(call_starts) == 2
        assert step_idx[1] < call_starts[1] < reasoning_end_idx[1], (
            "Tool call 2 must be between second STEP_STARTED and REASONING_MESSAGE_END"
        )


# ── Helper ──────────────────────────────────────────────────────────────────


async def _collect_orchestrator_events(
    corpora_config: CorporaConfig,
    slug: str = "eu-ai-act",
    model=None,
) -> list[object]:
    """Collect orchestrator events into a list."""
    from backend.agents.graph_orchestrator import run_orchestrator
    from backend.config import Settings

    settings = Settings(demo_disable_budget=True)

    events: list[object] = []
    async for event in run_orchestrator(
        messages=[{"role": "user", "content": "test query"}],
        corpus_slug=slug,
        corpora_config=corpora_config,
        settings=settings,
        thread_id="th-default",
        run_id="run-default",
        model=model,
    ):
        events.append(event)
    return events
