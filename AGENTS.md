## LangChain

For anything involving LangChain, read [LANGCHAIN.md](LANGCHAIN.md) first.

## File Paths

Whenever a path needs to be provided to a tool as an argument (e.g. to navigate or edit), always enclose path in "quotes", because spaces in the path string frequently occur.

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
