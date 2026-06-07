.PHONY: test test-quick check check-quick dev

check:  ## Run type checker and full test suite
	uv run pyright backend/ tests/ && uv run pytest && cd frontend && bun install --frozen-lockfile && bunx vitest run

check-quick:  ## Type check and run tests without re-syncing
	uv run pyright backend/ tests/ && uv run pytest && cd frontend && bunx vitest run

test:  ## Install test deps and run the full test suite
	uv sync --extra test && make check-quick

test-quick:  ## Run tests without re-syncing
	uv run pytest && cd frontend && bunx vitest run

dev:  ## Start the dev server (database, backend, frontend)
	./dev.sh

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
