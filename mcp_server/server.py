"""
server.py — JARVIS MCP Server Entry Point

Runs as an MCP server that thinking models connect to via stdio or SSE.
Exposes: tools (reflexes, exa, filesystem, composio), resources (context, status), prompts.
"""
import os
import sys
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

from mcp_server.tools_reflex import register_reflex_tools
from mcp_server.tools_browser import register_browser_tools
from mcp_server.tools_exa import register_exa_tools
from mcp_server.tools_fs import register_fs_tools
from mcp_server.tools_composio import register_composio_tools
from mcp_server.resources import register_resources
from mcp_server.prompts import register_prompts


def create_mcp_server(name="JARVIS Reflex MCP") -> "FastMCP":
    if FastMCP is None:
        raise ImportError("fastmcp not installed. Run: pip install fastmcp")

    mcp = FastMCP(name, log_level="WARNING")

    # Register all tool groups
    register_reflex_tools(mcp)
    register_browser_tools(mcp)
    register_exa_tools(mcp)
    register_fs_tools(mcp)
    register_composio_tools(mcp)

    # Register resources
    register_resources(mcp)

    # Register prompt templates
    register_prompts(mcp)

    return mcp


def run_stdio():
    """Run MCP server over stdio (for embedding in orchestrator or Claude Desktop)."""
    mcp = create_mcp_server()
    mcp.run(transport="stdio")


def run_sse(host="0.0.0.0", port=8001):
    """Run MCP server over SSE (for remote MCP clients)."""
    mcp = create_mcp_server()
    app = mcp.sse_app()
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.transport == "sse":
        run_sse(args.host, args.port)
    else:
        run_stdio()
