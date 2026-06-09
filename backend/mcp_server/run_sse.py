"""Run the MCP server with SSE transport.

Usage::

    uv run python -m backend.mcp_server.run_sse

Environment:
    MCP_HOST       — bind address (default: 0.0.0.0)
    MCP_PORT       — bind port     (default: 8082)
    MCP_LOG_LEVEL  — log level     (default: WARNING)
"""

import os
import logging

from backend.mcp_server.server import create_mcp_server

host = os.getenv("MCP_HOST", "0.0.0.0")
port = int(os.getenv("MCP_PORT", "8082"))
log_level = os.getenv("MCP_LOG_LEVEL", "WARNING").upper()

logging.basicConfig(level=getattr(logging, log_level, logging.WARNING))

srv = create_mcp_server(host=host, port=port)
srv.run(transport="sse")
