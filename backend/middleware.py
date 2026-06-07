"""Demo abuse-prevention middleware.

Three-layer defense:
  1. Caddy IP rate limiting (frontend/Caddyfile) — outermost
  2. Daily token budget (ASGI middleware) — checks /data/demo-budget.json
  3. Query validation (FastAPI middleware) — validates user message length & count
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# ── Budget File Helpers ──────────────────────────────────────────────────────


class BudgetFile:
    """Read/write the daily demo token budget file.

    Format: {"date": "2026-06-07", "tokens": 0}
    - Lazy-created on first access.
    - Auto-reset if ``date != today``.
    - Thread-safe enough for a demo (single uvicorn worker).
    """

    def __init__(self, path: str, daily_limit: int):
        self.path = path
        self.daily_limit = daily_limit

    def read(self) -> tuple[str, int]:
        """Return ``(date_str, tokens_used)``."""
        if not os.path.exists(self.path):
            self._write(today_str(), 0)
        with open(self.path) as f:
            data = json.load(f)
        d = data.get("date", "")
        t = data.get("tokens", 0)
        if d != today_str():
            self._write(today_str(), 0)
            return today_str(), 0
        return d, t

    def add_tokens(self, tokens: int) -> None:
        """Add *tokens* to the running total for today."""
        d, t = self.read()
        self._write(d, t + tokens)

    def is_exhausted(self) -> bool:
        """Return ``True`` if today's budget has been reached."""
        _, used = self.read()
        return used >= self.daily_limit

    def _write(self, d: str, tokens: int) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({"date": d, "tokens": tokens}, f)


def today_str() -> str:
    """Return today's date as ``YYYY-MM-DD`` (UTC)."""
    return date.fromtimestamp(datetime.now(timezone.utc).timestamp()).isoformat()


# ── Query Validation Middleware ──────────────────────────────────────────────


class QueryValidationMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that rejects requests with long or too-many user messages.

    Checks every user message in the chat request body against configured limits.
    Returns ``422 Unprocessable Entity`` with a clear error message on violation.
    """

    def __init__(self, app: ASGIApp, max_query_length: int, max_user_messages: int):
        super().__init__(app)
        self.max_query_length = max_query_length
        self.max_user_messages = max_user_messages

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/chat") and request.method == "POST":
            body = await request.body()
            try:
                payload = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return await call_next(request)

            user_msgs = [
                msg
                for msg in payload.get("messages", [])
                if isinstance(msg, dict) and msg.get("role", "user") == "user"
            ]

            # Check message count
            if len(user_msgs) > self.max_user_messages:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": (
                            f"Conversation exceeds the user message limit ({len(user_msgs)} sent vs "
                            f"{self.max_user_messages} allowed)."
                        )
                    },
                )

            # Check each user message length
            for msg in user_msgs:
                content = msg.get("content", "")
                if len(content) > self.max_query_length:
                    return JSONResponse(
                        status_code=422,
                        content={
                            "detail": (
                                f"User message exceeds maximum length "
                                f"({len(content)} > {self.max_query_length} characters)."
                            )
                        },
                    )

        return await call_next(request)


# ── Budget Middleware ─────────────────────────────────────────────────────────


class BudgetMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that returns 429 when the daily token budget is exhausted.

    The budget is incremented by the LLM client's ``usage_callback`` after
    each successful response — this middleware only performs a read-only
    check on the request path.
    """

    def __init__(self, app: ASGIApp, budget_file: BudgetFile):
        super().__init__(app)
        self.budget_file = budget_file

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/chat") and request.method == "POST":
            if self.budget_file.is_exhausted():
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Daily demo budget reached. Try again tomorrow.",
                    },
                )
        return await call_next(request)
