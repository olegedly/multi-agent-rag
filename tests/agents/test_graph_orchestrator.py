"""Tests for graph_orchestrator — multi-agent LangGraph pipeline.

Exercises ``run_orchestrator()`` with mocked ``agent.astream()`` to verify
state transitions, event shape with agent names, and correct
multi-agent orchestration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from ag_ui.core.events import (
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageStartEvent,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk

from backend.corpus_config import CorporaConfig


@pytest.fixture
def corpora_config():
    return CorporaConfig.from_dicts([
        {
            "id": "corpus-a-uuid",
            "slug": "eu-ai-act",
            "name": "EU AI Act",
            "description": "Test corpus",
            "chunker": "markdown-heading",
            "documents": "corpora/eu-ai-act/**/*.md",
        },
    ])


@pytest.fixture
def mock_model():
    """A fake BaseChatModel that sidesteps real API credentials."""
    return AsyncMock(spec=BaseChatModel)


# ── Tracer bullet 1: basic orchestration with three agents ──────────────────


@pytest.fixture
def mock_three_agents():
    """Mock create_agent so each agent yields text chunks with a distinct label.

    First agent yields "Researcher findings here", second yields "Critic "
    "feedback", third yields "Synthesized answer".  Uses a call counter to
    cycle through agents rather than fragile system_prompt text matching.
    """
    call_count: list[int] = [0]
    research_text = ["Researcher findings here"]
    critic_text = ["Critic ", "feedback"]
    synthesize_text = ["Synthesized answer"]

    def _make_astream(text_parts: list[str]):
        async def _astream(*args, **kwargs):
            for part in text_parts:
                yield AIMessageChunk(content=part), {"langgraph_node": "agent"}
        return _astream

    def _make_ainvoke(text_parts: list[str]):
        async def _ainvoke(*args, **kwargs):
            from langchain_core.messages import AIMessage
            return {"messages": [AIMessage(content="".join(text_parts))]}
        return _ainvoke

    agents_data = [
        (research_text,),
        (critic_text,),
        (synthesize_text,),
    ]

    def _create_agent_side_effect(*args, **kwargs):
        """Return a mock agent, cycling through agents by call order."""
        idx = call_count[0] % len(agents_data)
        call_count[0] += 1
        (text_parts,) = agents_data[idx]
        agent = AsyncMock()
        agent.astream = _make_astream(text_parts)
        agent.ainvoke = _make_ainvoke(text_parts)
        return agent

    with patch("langchain.agents.create_agent", side_effect=_create_agent_side_effect):
        yield


class TestBasicOrchestration:
    """run_orchestrator() yields correct events for three-agent flow."""

    async def test_emits_run_started_first(
        self, corpora_config, mock_three_agents, mock_model,
    ):
        """First event must be RunStartedEvent."""
        events = await _collect_orchestrator_events(
            corpora_config, model=mock_model,
        )
        assert len(events) >= 1
        assert isinstance(events[0], RunStartedEvent)

    async def test_emits_three_text_blocks(
        self, corpora_config, mock_three_agents, mock_model,
    ):
        """Three TEXT_MESSAGE_START events appear — one per agent."""
        events = await _collect_orchestrator_events(
            corpora_config, model=mock_model,
        )
        starts = [e for e in events if isinstance(e, TextMessageStartEvent)]
        assert len(starts) == 3

    async def test_agent_names_on_text_starts(
        self, corpora_config, mock_three_agents, mock_model,
    ):
        """Each TEXT_MESSAGE_START has the correct agent name."""
        events = await _collect_orchestrator_events(
            corpora_config, model=mock_model,
        )
        starts = [e for e in events if isinstance(e, TextMessageStartEvent)]
        names = [s.name for s in starts]
        assert names == ["Researcher", "Critic", "Synthesizer"]

    async def test_emits_run_finished_last(
        self, corpora_config, mock_three_agents, mock_model,
    ):
        """Last event must be a single RunFinishedEvent."""
        events = await _collect_orchestrator_events(
            corpora_config, model=mock_model,
        )
        finished = [e for e in events if isinstance(e, RunFinishedEvent)]
        assert len(finished) == 1
        assert events[-1] is finished[0]

    async def test_single_run_started(
        self, corpora_config, mock_three_agents, mock_model,
    ):
        """Only one RUN_STARTED event in the entire stream."""
        events = await _collect_orchestrator_events(
            corpora_config, model=mock_model,
        )
        starts = [e for e in events if isinstance(e, RunStartedEvent)]
        assert len(starts) == 1

    async def test_accrued_content_across_agents(
        self, corpora_config, mock_three_agents, mock_model,
    ):
        """All three agents' text content appears in the event stream."""
        events = await _collect_orchestrator_events(
            corpora_config, model=mock_model,
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
    """Mock create_agent so the first agent crashes mid-stream."""
    async def _astream(*args, **kwargs):
        yield AIMessageChunk(content="Before crash"), {"langgraph_node": "agent"}
        raise RuntimeError("API failure")

    async def _ainvoke(*args, **kwargs):
        from langchain_core.messages import AIMessage
        return {"messages": [AIMessage(content="Before crash")]}

    mock_agent = AsyncMock()
    mock_agent.astream = _astream
    mock_agent.ainvoke = _ainvoke

    with patch("langchain.agents.create_agent", return_value=mock_agent):
        yield


class TestOrchestratorErrors:
    """run_orchestrator() handles agent errors gracefully."""

    async def test_emits_run_error_on_crash(
        self, corpora_config, mock_first_agent_crash, mock_model,
    ):
        """When agent crashes, orchestrator yields RUN_ERROR."""
        events = await _collect_orchestrator_events(
            corpora_config, model=mock_model,
        )
        errors = [e for e in events if isinstance(e, RunErrorEvent)]
        assert len(errors) == 1

    async def test_no_run_finished_after_crash(
        self, corpora_config, mock_first_agent_crash, mock_model,
    ):
        """When agent crashes, no RUN_FINISHED event."""
        events = await _collect_orchestrator_events(
            corpora_config, model=mock_model,
        )
        finished = [e for e in events if isinstance(e, RunFinishedEvent)]
        assert len(finished) == 0


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
