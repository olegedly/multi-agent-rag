"""FastAPI application factory for multi-agent-rag.

Use ``create_app()`` to build the application with dependency injection
for testing. The factory accepts optional ``llm_client`` and ``settings``
parameters — when omitted they are created from environment variables.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
from fastapi import FastAPI
from google.adk.agents import Agent
from google.adk.tools.function_tool import FunctionTool

from backend.agents.tools import make_rag_tools
from backend.config import Settings, get_settings
from backend.corpus_config import CorporaConfig
from backend.llm.adk_adapter import AdkLlmAdapter
from backend.llm.factory import create_llm_client
from backend.llm.protocol import LLMClient
from backend.llm.transport import HttpTransport
from backend.middleware import BudgetStore, ChatGuard, JsonFileBudget


def create_app(
    llm_client: LLMClient | None = None,
    settings: Settings | None = None,
    corpora_config: CorporaConfig | None = None,
) -> FastAPI:
    """Build and return a configured FastAPI application.

    Parameters
    ----------
    llm_client : optional
        Inject a fake/stub client for testing. When ``None`` (default) the
        factory reads provider configuration from environment variables via
        :func:`create_llm_client`.
    settings : optional
        Override settings (e.g. for tests). When ``None``, reads from ``.env``.
    corpora_config : optional
        Injected config for testing. When ``None`` (default), loads from
        ``backend/corpora.yaml`` via :class:`CorporaConfig`.

    Returns
    -------
    FastAPI
        A fully wired application ready to serve or pass to ``TestClient``.
    """
    if settings is None:
        settings = get_settings()

    if corpora_config is None:
        corpora_config = CorporaConfig()

    # Collect transport references for lifespan cleanup
    transports: list[HttpTransport] = []

    # ------------------------------------------------------------------
    # LLM — injected via parameter (DI) or created from env config
    # ------------------------------------------------------------------
    if llm_client is None:
        llm_client = create_llm_client()

    transport = getattr(llm_client, "_transport", None)
    if isinstance(transport, HttpTransport):
        transports.append(transport)

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        for t in transports:
            await t.close()

    app = FastAPI(title=settings.app_name, lifespan=_lifespan)

    # ------------------------------------------------------------------
    # Daily token budget — shared between middleware (read) and
    # usage_callback (write).
    # ------------------------------------------------------------------
    budget_file: BudgetStore | None = None
    if not settings.demo_disable_budget:
        budget_file = JsonFileBudget(
            path=settings.demo_budget_file,
            daily_limit=settings.demo_daily_budget_tokens,
        )

        # Wire usage_callback so every LLM response increments the budget
        async def _record_usage(usage):
            budget_file.add_tokens(usage.input_tokens + usage.output_tokens)

        llm_client.usage_callback = _record_usage

    # ------------------------------------------------------------------
    # ChatGuard — single middleware for budget check + query validation.
    # Reads the body once, checks budget first (no body parsing needed
    # when exhausted), then validates user messages.
    # ------------------------------------------------------------------
    app.add_middleware(
        ChatGuard,
        max_query_length=settings.demo_max_query_length,
        max_user_messages=settings.demo_max_user_messages,
        budget_file=budget_file,  # ``None`` when budget disabled
    )

    llm_model = AdkLlmAdapter(llm_client)

    rag_search, rag_read_document = make_rag_tools()

    root_agent = Agent(
        name="rag_assistant",
        model=llm_model,
        instruction=(
            "You are a research assistant that answers questions exclusively from "
            "a curated knowledge base (the active corpus).\n\n"
            "Rules:\n"
            "1. Use the `rag_search` tool to find relevant chunks in the active "
            "corpus.  Use `rag_read_document` to retrieve full document context "
            "around promising chunks.\n"
            "2. Always cite your sources (corpus name + content excerpts + chunk IDs).\n"
            "3. If a search returns no results, say so — do not invent facts.\n"
            "4. **Refuse any question that has nothing to do with the active "
            "corpus's subject matter.**  Politely explain that you can only answer "
            "questions related to the loaded knowledge base.\n"
            "5. Never answer from your own pre-training knowledge — base every "
            "claim on a retrieved chunk."
        ),
        tools=[
            FunctionTool(rag_search),
            FunctionTool(rag_read_document),
        ],
    )

    adk_agent = ADKAgent(
        adk_agent=root_agent,
        app_name=settings.app_name,
        user_id="dev",
    )

    # Mounts POST /api/chat as AG-UI endpoint, plus GET /capabilities
    # and POST /agents/state
    add_adk_fastapi_endpoint(app, adk_agent, path="/api/chat")

    # ------------------------------------------------------------------
    # Corpus registry
    # ------------------------------------------------------------------
    @app.get("/api/corpora")
    async def list_corpora():
        """Return the list of available knowledge bases."""
        return corpora_config.list()

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    @app.get("/api/health")
    async def health():
        return {"app": settings.app_name, "status": "ok"}

    return app


# Module-level ``app`` for ``fastapi dev`` and ``fastapi run`` compatibility
_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """Lazy-init ``app`` so importing just ``backend.main`` (or its submodules)
    on CI doesn't crash from missing ``.env`` / env vars.

    ``fastapi dev``, ``fastapi run``, and ``uvicorn backend.main:app`` all
    trigger ``__getattr__("app")``, which creates the app on first access.
    Tests that ``from backend.main import create_app`` never trigger this.
    """
    if name == "app":
        global _app
        if _app is None:
            _app = create_app()
        return _app
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
