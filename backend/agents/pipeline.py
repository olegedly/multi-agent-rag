"""LangChain agent pipeline: Researcher -> Critic -> Synthesizer.

The pipeline runs a single-agent ``create_agent`` with RAG tools for
the Researcher role.  Future iterations will layer in the Critic and
Synthesizer after the initial results are gathered.
"""

from __future__ import annotations

import time
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from backend.corpus_config import CorporaConfig

# ---------------------------------------------------------------------------
# AG-UI protocol events
# ---------------------------------------------------------------------------
from ag_ui.core.events import (
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)


def _convert_dict_messages(messages: list[dict]) -> list[BaseMessage]:
    """Convert OpenAI chat-format dicts to LangChain BaseMessage objects."""
    lc_messages: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        elif role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "tool":
            lc_messages.append(
                ToolMessage(content=content, tool_call_id=msg.get("tool_call_id", ""))
            )
        else:
            lc_messages.append(HumanMessage(content=content))
    return lc_messages


async def run_pipeline(
    messages: list[dict],
    corpus_slug: str,
    corpora_config: CorporaConfig,
    settings,
    thread_id: str = "th-default",
    run_id: str = "run-default",
    model=None,
):
    """Run Researcher -> Critic -> Synthesizer.  Yields AG-UI protocol events.

    Parameters
    ----------
    messages : list[dict]
        The conversation history from the frontend (OpenAI chat format).
    corpus_slug : str
        URL slug for the corpus (e.g. ``"eu-ai-act"``).
    corpora_config : CorporaConfig
        Resolves the slug to a corpus UUID and metadata.
    settings : Settings
        App settings for LLM config.
    thread_id : str
        Thread identifier from the frontend.
    run_id : str
        Run identifier from the frontend.
    model : BaseChatModel, optional
        Pre-configured model instance.  When provided, ``ChatOpenAI``
        construction is skipped — useful for tests and for callers that
        want to wire their own model instance.

    Yields
    ------
    Pydantic AG-UI event models (serializable via ``EventEncoder.encode``):
        RunStartedEvent, TextMessageStartEvent, TextMessageContentEvent,
        TextMessageEndEvent, RunFinishedEvent, or RunErrorEvent.
    """
    corpus = corpora_config.get(corpus_slug)
    if corpus is None:
        return

    from backend.agents.langchain_tools import create_rag_tools
    from backend.middleware import JsonFileBudget, TokenBudgetCallback
    from langchain.agents import create_agent

    tools = create_rag_tools(corpus_id=corpus.id)

    # Wire daily token budget
    budget_file = None
    if not settings.demo_disable_budget:
        budget_file = JsonFileBudget(
            path=settings.demo_budget_file,
            daily_limit=settings.demo_daily_budget_tokens,
        )

    if model is None:
        from langchain_openai import ChatOpenAI

        # fmt: off
        model = ChatOpenAI(
            model=settings.llm_model,
            openai_api_key=settings.llm_api_key,  # type: ignore[call-arg]
            openai_api_base=settings.llm_base_url,  # type: ignore[call-arg]
            max_tokens=settings.llm_max_tokens,  # type: ignore[call-arg]
            temperature=0,
            callbacks=[TokenBudgetCallback(budget_file)],
        )
        # fmt: on

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=(
            "You are a research assistant that answers questions exclusively from "
            "a curated knowledge base (the active corpus).\n\n"
            "Rules:\n"
            f"1. Use the `rag_search` tool to find relevant chunks in the corpus '{corpus.name}'.\n"
            "2. Use `rag_read_document` to retrieve full document context around promising chunks.\n"
            "3. Always cite your sources (corpus name + content excerpts + chunk IDs).\n"
            "4. If a search returns no results, say so — do not invent facts.\n"
            "5. Never answer from your own pre-training knowledge — base every claim on a retrieved chunk."
        ),
    )

    lc_messages = _convert_dict_messages(messages)

    message_id = str(uuid4())
    ts = int(time.time() * 1000)

    yield RunStartedEvent(thread_id=thread_id, run_id=run_id, timestamp=ts)

    result = await agent.ainvoke(
        {"messages": lc_messages},  # type: ignore[arg-type]
        config={"recursion_limit": 25},
    )

    content = ""
    last_msg = result["messages"][-1] if result["messages"] else None
    if last_msg and hasattr(last_msg, "content") and last_msg.content:
        content = last_msg.content

    if content:
        yield TextMessageStartEvent(message_id=message_id, role="assistant", timestamp=ts)
        yield TextMessageContentEvent(message_id=message_id, delta=content, timestamp=ts)
        yield TextMessageEndEvent(message_id=message_id, timestamp=ts)

    yield RunFinishedEvent(
        thread_id=thread_id,
        run_id=run_id,
        timestamp=ts,
        finishReason="stop",  # type: ignore[call-arg]
        usage={"promptTokens": 0, "completionTokens": 0},  # type: ignore[call-arg]
    )
