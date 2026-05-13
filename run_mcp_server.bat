@echo off
title JARVIS MCP Server
cd /d "%~dp0"

echo ========================================
echo JARVIS MCP Server
echo Exposes ~270 PC/browser reflexes, Exa
echo research, filesystem, and Composio tools
echo to any MCP-compatible LLM client.
echo ========================================
echo.
echo Transport: %1 (default: stdio)
echo.

if not exist "venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found.
    pause
    exit /b 1
)

set KMP_DUPLICATE_LIB_OK=TRUE

if /i "%1"=="sse" (
    echo Starting MCP server over SSE on port %2 (default: 8001)
    venv\Scripts\python.exe -m mcp_server.server --transport sse --port %~2
) else (
    echo Starting MCP server over stdio (for Claude Desktop / Cursor)
    venv\Scripts\python.exe -m mcp_server.server --transport stdio
)

pause
