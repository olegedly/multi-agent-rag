#!/bin/bash
set -e

cleanup() {
  echo ""
  echo "Shutting down..."
  docker compose down
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  [ -n "$PGWEB_PID" ] && kill "$PGWEB_PID" 2>/dev/null
  [ -n "$MCP_PID" ] && kill "$MCP_PID" 2>/dev/null
  exit 0
}
trap cleanup SIGINT SIGTERM

# Source .env so native tools inherit DB credentials
# shellcheck disable=SC1091
[ -f .env ] && set -a && source .env && set +a

# ── Database (Docker) ──────────────────────────────────────
echo "Starting PostgreSQL (pgvector)..."
docker compose up -d

echo "Waiting for PostgreSQL to be healthy..."
until docker compose exec db pg_isready -U "$POSTGRES_USER" --quiet 2>/dev/null; do
  sleep 1
done
echo "PostgreSQL is ready."

# ── pgweb (native) ─────────────────────────────────────────
echo "Starting pgweb (PostgreSQL GUI)..."
pgweb \
  --host "$POSTGRES_HOST" \
  --db "$POSTGRES_DB" \
  --user "$POSTGRES_USER" \
  --pass "$POSTGRES_PASSWORD" \
  --port "$POSTGRES_PORT" &
PGWEB_PID=$!
echo "pgweb GUI → http://127.0.0.1:8081"

# ── Backend (native, hot-reload) ───────────────────────────
echo "Starting backend (fastapi dev)..."
# Disable daily token budget in dev — backend runs natively, not in Docker
# (so /data/demo-budget.json doesn't exist). Query validation stays active.
export DEMO_DISABLE_BUDGET=true
uv run fastapi dev --port 8000 --host 0.0.0.0 &
BACKEND_PID=$!

echo "Waiting for backend to be ready..."
for i in $(seq 1 30); do
  if curl -s -o /dev/null http://127.0.0.1:8000/api/health 2>/dev/null; then
    echo "Backend is ready."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Backend failed to start within 30 seconds."
    kill "$BACKEND_PID" 2>/dev/null
    exit 1
  fi
  sleep 1
done

# ── MCP server (SSE) ────────────────────────────────────────
echo "Starting MCP server (SSE, port 8082)..."
export MCP_HOST=0.0.0.0
MCP_PORT=8082 MCP_LOG_LEVEL=WARNING \
  uv run python -m backend.mcp_server.run_sse &
MCP_PID=$!
echo "MCP server SSE → http://127.0.0.1:8082/sse"
echo "MCP server messages → http://127.0.0.1:8082/messages/"

# ── Frontend (Vite) ────────────────────────────────────────
echo "Starting frontend (Vite dev server)..."
bun run --cwd frontend dev
