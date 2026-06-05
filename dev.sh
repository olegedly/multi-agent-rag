#!/bin/bash
set -e

cleanup() {
  echo ""
  echo "Shutting down..."
  docker compose -f docker-compose.base.yml -f docker-compose.dev-override.yml down
  exit 0
}
trap cleanup SIGINT SIGTERM

echo "Starting backend (FastAPI + PostgreSQL)..."
docker compose -f docker-compose.base.yml -f docker-compose.dev-override.yml up -d

echo "Starting frontend (Vite dev server)..."
bun run --cwd frontend dev
