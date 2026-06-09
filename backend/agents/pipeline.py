"""LangChain agent pipeline: Researcher → Critic → Synthesizer.

The pipeline runs a single-agent ``create_agent`` with RAG tools for
the Researcher role.  Future iterations will layer in the Critic and
Synthesizer after the initial results are gathered.
"""

from __future__ import annotations

from typing import AsyncIterable

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from backend.corpus_config import CorporaConfig


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
    settings=None,
) -> AsyncIterable[dict]:
    """Run Researcher → Critic → Synthesizer.  Yields TanStack SSE events.

    Parameters
    ----------
    messages : list[dict]
        The conversation history from the frontend (OpenAI chat format).
    corpus_slug : str
        URL slug for the corpus (e.g. ``"eu-ai-act"``).
    corpora_config : CorporaConfig
        Resolves the slug to a corpus UUID and metadata.
    settings : Settings, optional
        App settings for LLM config.  Created lazily if ``None``.

    Yields
    ------
    dict
        TanStack AI SSE event dicts: ``content``, ``tool_call``, ``done``.
    """
    corpus = corpora_config.get(corpus_slug)
    if corpus is None:
        return

    if settings is None:
        from backend.config import get_settings

        settings = get_settings()

    from backend.agents.langchain_tools import create_rag_tools
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI

    tools = create_rag_tools(corpus_id=corpus.id)

    # fmt: off
    model = ChatOpenAI(
        model=settings.llm_model,
        openai_api_key=settings.llm_api_key,  # type: ignore[call-arg]
        openai_api_base=settings.llm_base_url,  # type: ignore[call-arg]
        max_tokens=settings.llm_max_tokens,  # type: ignore[call-arg]
        temperature=0,
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

    result = await agent.ainvoke(
        {"messages": lc_messages},  # type: ignore[arg-type]
        config={"recursion_limit": 25},
    )

    content = ""
    last_msg = result["messages"][-1] if result["messages"] else None
    if last_msg and hasattr(last_msg, "content") and last_msg.content:
        content = last_msg.content

    if content:
        yield {
            "type": "content",
            "delta": content,
            "content": content,
            "role": "assistant",
        }

    yield {
        "type": "done",
        "finishReason": "stop",
        "usage": {"promptTokens": 0, "completionTokens": 0},
    }
