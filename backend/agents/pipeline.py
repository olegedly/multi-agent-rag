"""LangChain agent pipeline: Researcher → Critic → Synthesizer.

The pipeline runs a single-agent ``create_agent`` with RAG tools for
the Researcher role.  Future iterations will layer in the Critic and
Synthesizer after the initial results are gathered.
"""

from __future__ import annotations

from typing import AsyncIterable

from backend.corpus_config import CorporaConfig
from backend.embeddings.factory import create_embedding_client
from backend.rag.search import AsyncSessionMaker
from backend.db import create_db_sessionmaker


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

    model = ChatOpenAI(
        model=settings.llm_model,
        openai_api_key=settings.llm_api_key,
        openai_api_base=settings.llm_base_url,
        max_tokens=settings.llm_max_tokens,
        temperature=0,
    )

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

    result = await agent.ainvoke(
        {"messages": messages},
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
