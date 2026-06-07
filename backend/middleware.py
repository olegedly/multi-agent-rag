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


# ── Chat Guard Middleware ─────────────────────────────────────────────────────


class ChatGuard(BaseHTTPMiddleware):
    """Combined pre-chat guard: budget check + query validation.

    Guards all ``POST /api/chat`` requests.  Reads the body once and runs both
    checks before forwarding to the app:

    1. Budget check — short-circuits with 429 before parsing the body when
       the daily token budget is exhausted.  Skipped when *budget_file* is
       ``None`` (budget disabled).
    2. Query validation — parses the AG-UI message format, checks user message
       length and count, returns 422 on violation.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_query_length: int,
        max_user_messages: int,
        budget_file: BudgetFile | None = None,
    ):
        super().__init__(app)
        self.max_query_length = max_query_length
        self.max_user_messages = max_user_messages
        self.budget_file = budget_file

    async def dispatch(self, request: Request, call_next):
        if not (request.url.path.startswith("/api/chat") and request.method == "POST"):
            return await call_next(request)

        # 1. Budget check — fast path, no body parsing
        if self.budget_file is not None and self.budget_file.is_exhausted():
            return JSONResponse(
                status_code=429,
                content={"detail": "Daily demo budget reached. Try again tomorrow."},
            )

        # 2. Parse body and validate
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
