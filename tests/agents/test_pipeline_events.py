"""Tests for pipeline AG-UI event emission.

Exercises ``run_pipeline()`` with a mocked ``agent.ainvoke()`` to verify
the correct sequence and shape of AG-UI protocol events.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from ag_ui.core.events import (
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from langchain_core.messages import AIMessage

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


# ── Tracer bullet: run_pipeline yields correct AG-UI events ─────────────────


class TestPipelineEvents:
    """run_pipeline() yields AG-UI protocol events in correct order."""

    @pytest.fixture
    def mock_agent(self):
        """Mock create_agent and ChatOpenAI so no real LLM call happens."""
        fake_result = {
            "messages": [AIMessage(content="Hello from the agent")],
        }
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = fake_result

        with patch("langchain.agents.create_agent", return_value=mock_agent):
            yield

    async def test_emits_run_started_first(self, corpora_config, mock_agent):
        """First event must be RunStartedEvent with thread/run IDs."""
        events = await collect_pipeline_events(corpora_config)
        assert len(events) >= 1
        first = events[0]
        assert isinstance(first, RunStartedEvent)
        assert first.thread_id == "th-default"
        assert first.run_id == "run-default"
        assert first.timestamp is not None

    async def test_emits_text_message_events(self, corpora_config, mock_agent):
        """Content messages yield TEXT_MESSAGE_START/CONTENT/END."""
        events = await collect_pipeline_events(corpora_config)

        text_events = [
            e
            for e in events
            if isinstance(e, (TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent))
        ]
        assert len(text_events) >= 1

        starts = [e for e in text_events if isinstance(e, TextMessageStartEvent)]
        assert len(starts) == 1
        assert starts[0].role == "assistant"

        contents = [e for e in text_events if isinstance(e, TextMessageContentEvent)]
        assert len(contents) == 1
        assert contents[0].delta == "Hello from the agent"

        ends = [e for e in text_events if isinstance(e, TextMessageEndEvent)]
        assert len(ends) == 1

    async def test_emits_run_finished_last(self, corpora_config, mock_agent):
        """Last event must be RunFinishedEvent."""
        events = await collect_pipeline_events(corpora_config)

        last = events[-1]
        assert isinstance(last, RunFinishedEvent)
        assert last.thread_id == "th-default"
        assert last.run_id == "run-default"
        assert last.finishReason == "stop"  # type: ignore[attr-defined]

    async def test_full_event_sequence(self, corpora_config, mock_agent):
        """Verify complete event type sequence."""
        events = await collect_pipeline_events(corpora_config)

        types = [type(e).__name__ for e in events]
        assert types == [
            "RunStartedEvent",
            "TextMessageStartEvent",
            "TextMessageContentEvent",
            "TextMessageEndEvent",
            "RunFinishedEvent",
        ]

    async def test_empty_content_skips_text_events(self, corpora_config):
        """When agent returns no content, no TEXT_MESSAGE events are emitted."""
        fake_result = {
            "messages": [AIMessage(content="")],
        }
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = fake_result

        with patch("langchain.agents.create_agent", return_value=mock_agent):
            events = await collect_pipeline_events(corpora_config)

        types = [type(e).__name__ for e in events]
        assert "TextMessageStartEvent" not in types
        assert "TextMessageContentEvent" not in types
        assert "TextMessageEndEvent" not in types
        assert types[-1] == "RunFinishedEvent"

    async def test_unknown_corpus_returns_no_events(self, corpora_config):
        """Unknown corpus slug yields zero events."""
        events = await collect_pipeline_events(corpora_config, slug="nonexistent")
        assert events == []


# ── Helper ───────────────────────────────────────────────────────────────────


async def collect_pipeline_events(
    corpora_config: CorporaConfig,
    slug: str = "eu-ai-act",
) -> list[object]:
    """Collect pipeline events into a list."""
    from backend.agents.pipeline import run_pipeline

    events: list[object] = []
    async for event in run_pipeline(
        messages=[{"role": "user", "content": "test"}],
        corpus_slug=slug,
        corpora_config=corpora_config,
        thread_id="th-default",
        run_id="run-default",
    ):
        events.append(event)
    return events
