"""StreamEventHandler — token-level AG-UI event builder from stream chunks.

Two-phase ``observe()`` / ``drain()`` pattern decouples chunk processing
from event emission for clean testability.
"""

from __future__ import annotations

import time
from typing import cast
from uuid import uuid4

from ag_ui.core.events import (
    BaseEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from langchain_core.messages import AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.messages.tool import ToolCallChunk


class StreamEventHandler:
    """Observe stream chunks and drain AG-UI events.

    Phases
    ------
        1. Construct  →  first ``drain()`` yields ``RUN_STARTED``.
        2. For each ``(chunk, metadata)`` from ``astream``:
           ``observe(chunk, metadata)`` → ``drain()``.
        3. After stream exhausts:
           ``finalize()`` → closes open blocks, yields ``RUN_FINISHED``.
           Or ``error(message)`` → closes blocks, yields ``RUN_ERROR``.

    Only a single text message and a single reasoning block are supported
    (typical for single ``create_agent()`` pipelines).  Tool calls may be
    concurrent (tracked independently by id).
    """

    def __init__(
        self,
        thread_id: str,
        run_id: str,
        message_id: str | None = None,
        agent_name: str | None = None,
        suppress_run_started: bool = False,
    ) -> None:
        self._thread_id = thread_id
        self._run_id = run_id
        self._message_id = message_id or str(uuid4())
        self._agent_name = agent_name
        # Open block tracking
        self._text_open = False
        self._reasoning_open = False
        self._open_tool_ids: set[str] = set()
        # ToolCallChunks that follow a TOOL_CALL_START often carry only
        # `args` with `id=None`/`name=None` (LangGraph merges by index).
        # Track the last known id per index to fill in the gap.
        self._last_tool_call_id_by_index: dict[int, str] = {}

        # Accumulated reasoning content for delta computation
        # (DeepSeek sends full accumulated text in each chunk)
        self._last_reasoning_content: str = ""

        # Step counter for unique STEP_STARTED stepIds per reasoning block
        self._reasoning_step_counter: int = 0
        self._current_reasoning_step_id: str | None = None

        # Draining — run_started is buffered on construction unless suppressed
        self._pending: list[BaseEvent] = []
        if not suppress_run_started:
            self._pending = [
                RunStartedEvent(
                    thread_id=thread_id,
                    run_id=run_id,
                    timestamp=_now_ms(),
                ),
            ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe(self, chunk: BaseMessage, metadata: dict) -> None:
        """Process one stream chunk and enqueue events.

        Parameters
        ----------
        chunk : BaseMessage
            An ``AIMessageChunk`` (text/calls) or ``ToolMessage`` (results).
        metadata : dict
            LangGraph node metadata (e.g. ``{"langgraph_node": "agent"}``).
        """
        if isinstance(chunk, AIMessageChunk):
            self._observe_ai_chunk(chunk)
        elif isinstance(chunk, ToolMessage):
            self._observe_tool_result(chunk)

    def drain(self) -> list[BaseEvent]:
        """Return all buffered events and clear the pending queue."""
        events = self._pending
        self._pending = []
        return events

    def finalize(self) -> list[BaseEvent]:
        """Close any open blocks and emit ``RUN_FINISHED``.

        Returns
        -------
        list[BaseEvent]
            Closing events followed by ``RunFinishedEvent``.
        """
        self._close_reasoning()
        self._close_text()
        self._close_all_tools()

        self._pending.append(
            RunFinishedEvent(
                thread_id=self._thread_id,
                run_id=self._run_id,
                timestamp=_now_ms(),
            ),
        )
        return self.drain()

    def error(self, message: str) -> list[BaseEvent]:
        """Close open blocks and emit ``RUN_ERROR``.

        Parameters
        ----------
        message : str
            Error description.

        Returns
        -------
        list[BaseEvent]
            Closing events followed by ``RunErrorEvent``.
        """
        self._close_reasoning()
        self._close_text()
        self._close_all_tools()

        self._pending.append(
            RunErrorEvent(message=message, timestamp=_now_ms()),
        )
        return self.drain()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _observe_ai_chunk(self, chunk: AIMessageChunk) -> None:
        """Dispatch an ``AIMessageChunk`` to reasoning / text / tool handlers."""
        # Reasoning (if present)
        raw_reasoning = chunk.additional_kwargs.get("reasoning_content")
        if raw_reasoning and isinstance(raw_reasoning, str):
            self._close_text()  # can't interleave, but text may be open
            self._ensure_reasoning_open()
            # DeepSeek sends the full accumulated reasoning_content in each
            # chunk. Diff against the previous text and emit only the new portion.
            if raw_reasoning.startswith(self._last_reasoning_content):
                delta = raw_reasoning[len(self._last_reasoning_content):]
            else:
                delta = raw_reasoning  # can't diff, emit full text
            self._last_reasoning_content = raw_reasoning
            if delta:
                self._pending.append(
                    ReasoningMessageContentEvent(
                        message_id=self._message_id,
                        delta=delta,
                        **{"stepId": self._current_reasoning_step_id or ""},  # type: ignore[arg-type]
                    ),
                )
            return  # reasoning chunks usually carry no content or tool calls

        # Tool call chunks
        if chunk.tool_call_chunks:
            for tcc in chunk.tool_call_chunks:
                tid = tcc.get("id")
                idx = tcc.get("index")
                # LangGraph merges tool_call_chunks by index; subsequent
                # merged chunks have id=None but still carry args. Fall
                # back to the last known id for this index.
                if not tid and idx is not None and idx in self._last_tool_call_id_by_index:
                    tid = self._last_tool_call_id_by_index[idx]
                if tid and idx is not None:
                    self._last_tool_call_id_by_index[idx] = tid

                self._ensure_tool_open(tcc, resolved_id=tid)
                self._pending.append(
                    ToolCallArgsEvent(
                        tool_call_id=tid or "",
                        delta=tcc["args"] or "",
                    ),
                )
            # If there's also text content alongside tool calls, emit it
            # but make sure text block is open.
            raw_content = chunk.content
            if raw_content:
                self._ensure_text_open()
                delta = cast(str, raw_content) if isinstance(raw_content, str) else ""
                self._pending.append(
                    TextMessageContentEvent(
                        message_id=self._message_id,
                        delta=delta,
                    ),
                )
            return

        # Plain text content
        raw_content = chunk.content
        if raw_content:
            self._close_reasoning()
            self._ensure_text_open()
            delta = cast(str, raw_content) if isinstance(raw_content, str) else ""
            self._pending.append(
                TextMessageContentEvent(
                    message_id=self._message_id,
                    delta=delta,
                ),
            )

    def _observe_tool_result(self, chunk: ToolMessage) -> None:
        """Emit TOOL_CALL_END + TOOL_CALL_RESULT for a ToolMessage.

        Also closes any open reasoning block — the next reasoning phase
        from the LLM should start a fresh REASONING_MESSAGE block, not
        accumulate into the previous one.
        """
        self._close_reasoning()
        tid = chunk.tool_call_id or ""
        raw_content = chunk.content
        self._open_tool_ids.discard(tid)
        self._pending.append(
            ToolCallEndEvent(tool_call_id=tid, timestamp=_now_ms()),
        )
        content_str = cast(str, raw_content) if isinstance(raw_content, str) else ""
        self._pending.append(
            ToolCallResultEvent(
                message_id=self._message_id,
                tool_call_id=tid,
                content=content_str,
            ),
        )

    def _ensure_reasoning_open(self) -> None:
        """Emit ``STEP_STARTED`` + ``REASONING_MESSAGE_START`` if not yet open.

        ``STEP_STARTED`` with a unique ``stepId`` is required because the
        frontend's ``StreamProcessor`` ignores ``REASONING_MESSAGE_START``/``END``
        — those are ``break;`` no-ops. Instead it keys thinking parts by
        ``stepId``, which must be set via ``STEP_STARTED`` so consecutive
        reasoning blocks produce separate ``ThinkingPart`` elements in the UI.
        """
        if not self._reasoning_open:
            self._reasoning_open = True
            step_id = f"rs-{self._message_id}-{self._reasoning_step_counter}"
            self._reasoning_step_counter += 1
            self._current_reasoning_step_id = step_id
            self._pending.append(
                StepStartedEvent(step_name="reasoning", **{"stepId": step_id}),  # type: ignore[call-arg]
            )
            self._pending.append(
                ReasoningMessageStartEvent(
                    message_id=self._message_id,
                    role="reasoning",
                ),
            )

    def _ensure_text_open(self) -> None:
        """Emit ``TEXT_MESSAGE_START`` if not yet open."""
        if not self._text_open:
            self._text_open = True
            self._pending.append(
                TextMessageStartEvent(
                    message_id=self._message_id,
                    role="assistant",
                    name=self._agent_name,
                    timestamp=_now_ms(),
                ),
            )

    def _ensure_tool_open(self, tcc: ToolCallChunk, resolved_id: str | None = None) -> None:
        """Emit ``TOOL_CALL_START`` for a tool if not yet tracked."""
        tid = resolved_id or tcc.get("id") or ""
        if tid and tid not in self._open_tool_ids:
            self._open_tool_ids.add(tid)
            self._pending.append(
                ToolCallStartEvent(
                    tool_call_id=tid,
                    tool_call_name=tcc.get("name") or "",
                    timestamp=_now_ms(),
                ),
            )

    def _close_reasoning(self) -> None:
        if self._reasoning_open:
            self._reasoning_open = False
            self._last_reasoning_content = ""
            self._current_reasoning_step_id = None
            self._pending.append(
                ReasoningMessageEndEvent(message_id=self._message_id),
            )

    def _close_text(self) -> None:
        if self._text_open:
            self._text_open = False
            self._pending.append(
                TextMessageEndEvent(message_id=self._message_id),
            )

    def _close_all_tools(self) -> None:
        for tid in list(self._open_tool_ids):
            self._open_tool_ids.discard(tid)
            self._pending.append(
                ToolCallEndEvent(tool_call_id=tid, timestamp=_now_ms()),
            )


def _now_ms() -> int:
    return int(time.time() * 1000)
