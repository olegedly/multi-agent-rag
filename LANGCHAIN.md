# LangChain + Deep Agents Development Guide

This project uses skills that contain up-to-date patterns and working reference scripts.

## CRITICAL: Invoke Skills BEFORE Writing Code

**ALWAYS** invoke the relevant skill first - skills have the correct imports, patterns, and scripts that prevent common mistakes.

### Getting Started

- **ecosystem-primer** - Invoke FIRST for any LangChain/LangGraph/Deep Agents project: framework selection, env setup, and which skill to load next
- **langchain-dependencies** - Invoke before installing packages or when resolving version issues (Python + TypeScript)

### LangChain Skills

- **langchain-fundamentals** - Invoke for create_agent, @tool decorator, middleware patterns
- **langchain-rag** - Invoke for RAG pipelines, vector stores, embeddings
- **langchain-middleware** - Invoke for structured output with Pydantic

### LangGraph Skills

- **langgraph-cli** - Invoke for langgraph CLI commands: new, dev, build, up, deploy, and langgraph.json configuration
- **langgraph-fundamentals** - Invoke for StateGraph, state schemas, edges, Command, Send, invoke, streaming, error handling
- **langgraph-persistence** - Invoke for checkpointers, thread_id, time travel, memory, subgraph scoping
- **langgraph-human-in-the-loop** - Invoke for interrupts, human review, error handling, approval workflows

### Deep Agents Skills

- **deep-agents-core** - Invoke for Deep Agents harness architecture
- **deep-agents-memory** - Invoke for long-term memory with StoreBackend
- **deep-agents-orchestration** - Invoke for multi-agent coordination
- **managed-deep-agents** - Invoke for Managed Deep Agents: deploy with the CLI, use the SDKs, stream runs, connect MCP tools, and build React `useStream` UIs

## MCP

You have access to an MCP server called "langchain" with these tools:

1. langchain_search_docs_by_lang_chain - Search across the Docs by LangChain knowledge
2. langchain_query_docs_filesystem_docs_by_lang_chain - Run a read-only shell-like query against a...
3. langchain_get_langchain - Use when building AI agents with LLMs, creating...

Use them.
