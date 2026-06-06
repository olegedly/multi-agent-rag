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

from backend.config import Settings, get_settings
from backend.llm.adk_adapter import AdkLlmAdapter
from backend.llm.factory import create_llm_client
from backend.llm.protocol import LLMClient
from backend.llm.transport import HttpTransport


def create_app(
    llm_client: LLMClient | None = None,
    settings: Settings | None = None,
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

    Returns
    -------
    FastAPI
        A fully wired application ready to serve or pass to ``TestClient``.
    """
    if settings is None:
        settings = get_settings()

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

    llm_model = AdkLlmAdapter(llm_client)

    root_agent = Agent(
        name="rag_assistant",
        model=llm_model,
        instruction=(
            "You are a helpful research assistant. "
            "Answer questions clearly and concisely."
        ),
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
    # Health check
    # ------------------------------------------------------------------
    @app.get("/api/health")
    async def health():
        return {"app": settings.app_name, "status": "ok"}

    return app


# Module-level ``app`` for ``fastapi dev`` and ``fastapi run`` compatibility
app = create_app()
