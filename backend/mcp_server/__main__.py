"""Entry point for the RAG MCP server.

Run::

    uv run python -m backend.mcp_server
"""

from .server import mcp

mcp.run(transport="stdio")
