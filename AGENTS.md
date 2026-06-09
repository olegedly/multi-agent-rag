## LangChain

For anything involving LangChain, read [LANGCHAIN.md](LANGCHAIN.md) first.

## File Paths

Whenever a path needs to be provided to a tool as an argument (e.g. to navigate or edit), always enclose path in "quotes", because spaces in the path string frequently occur.

## Development Environment

Do not manage processes related to starting or killing development servers or anything of that sort. Assume all the right services are running. If you find that they don't, stop and ask the user to start them. Both the backend and the frontend have hot module reloading, so just editing files is sufficient. Your changes propagate immediately. If doing browser control via CDP, assume the right tab is already open. Work with it via UI interaction.

## Testing — This Is the Only Way

Use `make test`, `make test_backend`, or `make test_frontend`. Never invoke
pytest, pyright, tsc, or vitest directly. These Make targets are the sole
official testing interface — during TDD, before every commit, for CI.

```
make test_backend    # uv sync + pyright + pytest          — backend only
make test_frontend   # bun install + tsc + vitest           — frontend only
make test            # test_backend + test_frontend in sequence
make -j2 test_backend test_frontend  # parallel
```

Every target is comprehensive: install deps → type-check → run all tests.
There are no quick or partial variants. Any change passes the full gate.
