"""FastAPI application factory for multi-agent-rag.

Use ``create_app()`` to build the application with dependency injection
for testing.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from backend.agents.pipeline import run_pipeline
from backend.config import Settings, get_settings
from backend.corpus_config import CorporaConfig
from backend.middleware import BudgetStore, ChatGuard, JsonFileBudget


def create_app(
    settings: Settings | None = None,
    corpora_config: CorporaConfig | None = None,
) -> FastAPI:
    """Build and return a configured FastAPI application.

    Parameters
    ----------
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

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(title=settings.app_name, lifespan=_lifespan)

    # ------------------------------------------------------------------
    # Daily token budget
    # ------------------------------------------------------------------
    budget_file: BudgetStore | None = None
    if not settings.demo_disable_budget:
        budget_file = JsonFileBudget(
            path=settings.demo_budget_file,
            daily_limit=settings.demo_daily_budget_tokens,
        )

    # ------------------------------------------------------------------
    # ChatGuard middleware
    # ------------------------------------------------------------------
    app.add_middleware(
        ChatGuard,
        max_query_length=settings.demo_max_query_length,
        max_user_messages=settings.demo_max_user_messages,
        budget_file=budget_file,
    )

    # ------------------------------------------------------------------
    # Chat endpoint — POST /api/chat/{slug}
    # ------------------------------------------------------------------
    @app.post("/api/chat/{slug}")
    async def chat(slug: str, request: Request):
        """Stream a response from the RAG agent pipeline.

        Accepts TanStack AI ``fetchServerSentEvents`` POST format:
        ``{ messages: [...], forwardedProps?: { corpusId } }``.
        """
        corpus = corpora_config.get(slug)
        if corpus is None:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=404,
                content={"detail": f"Unknown corpus slug: {slug!r}"},
            )

        body = await request.json()
        messages = body.get("messages", [])

        async def _stream():
            try:
                async for event in run_pipeline(
                    messages, slug, corpora_config=corpora_config, settings=settings,
                ):
                    yield f"data: {json.dumps(event)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'error': {'message': str(exc)}})}\n\n"

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

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


# Module-level ``app`` for ``fastapi dev``
_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        global _app
        if _app is None:
            _app = create_app()
        return _app
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
