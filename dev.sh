#!/bin/bash
set -e

cleanup() {
  echo ""
  echo "Shutting down..."
  docker compose -f docker-compose.base.yml -f docker-compose.dev-override.yml down
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  exit 0
}
trap cleanup SIGINT SIGTERM

# ── Database (Docker) ──────────────────────────────────────
echo "Starting PostgreSQL (pgvector)..."
docker compose -f docker-compose.base.yml -f docker-compose.dev-override.yml up -d db

echo "Waiting for PostgreSQL to be healthy..."
until docker compose -f docker-compose.base.yml -f docker-compose.dev-override.yml exec db pg_isready -U "${POSTGRES_USER:-postgres}" --quiet 2>/dev/null; do
  sleep 1
done
echo "PostgreSQL is ready."

# ── Backend (native, hot-reload) ───────────────────────────
echo "Starting backend (fastapi dev)..."
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

# ── Frontend (Vite) ────────────────────────────────────────
echo "Starting frontend (Vite dev server)..."
bun run --cwd frontend dev
