# JARVIS MCP Server
param(
    [ValidateSet("stdio", "sse")]
    [string]$Transport = "stdio",
    [int]$Port = 8001
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "JARVIS MCP Server" -ForegroundColor Cyan
Write-Host "Exposes ~270 PC/browser reflexes, Exa" -ForegroundColor Cyan
Write-Host "research, filesystem, and Composio tools" -ForegroundColor Cyan
Write-Host "to any MCP-compatible LLM client." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "ERROR: Virtual environment not found." -ForegroundColor Red
    exit 1
}

$env:KMP_DUPLICATE_LIB_OK = "TRUE"

if ($Transport -eq "sse") {
    Write-Host "Starting MCP server over SSE on port $Port" -ForegroundColor Green
    & "venv\Scripts\python.exe" -m mcp_server.server --transport sse --port $Port
} else {
    Write-Host "Starting MCP server over stdio (for Claude Desktop / Cursor)" -ForegroundColor Green
    & "venv\Scripts\python.exe" -m mcp_server.server --transport stdio
}
