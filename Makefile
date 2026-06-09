.PHONY: test test_backend test_frontend dev copy-corpus-data help

test: test_backend test_frontend  ## Full test suite (backend + frontend)

test_backend:  ## Backend: install deps, type-check, run tests
	uv sync --extra test
	uv run pyright backend/ tests/
	uv run pytest

test_frontend:  ## Frontend: install deps, type-check, run tests
	cd frontend && bun install --frozen-lockfile && bunx tsc --noEmit && bunx vitest run

dev:  ## Start the dev server (database, backend, frontend)
	./dev.sh

copy-corpus-data:  ## Copy corpus data from dev to Supabase (no re-embedding)
	uv run python scripts/copy_corpus_data.py

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
