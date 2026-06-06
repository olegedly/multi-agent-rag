.PHONY: test test-quick dev

test:  ## Install test deps and run the full test suite
	uv sync --extra test && uv run pytest && cd frontend && bun install --frozen-lockfile && bunx vitest run

test-quick:  ## Run tests without re-syncing
	uv run pytest && cd frontend && bunx vitest run

dev:  ## Start the dev server (database, backend, frontend)
	./dev.sh

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
