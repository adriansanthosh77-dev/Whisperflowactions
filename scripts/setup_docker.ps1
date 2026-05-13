param()

$ErrorActionPreference = "Stop"

Write-Host "=== JARVIS Docker Setup ==="

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Docker is not installed." -ForegroundColor Red
    Write-Host "Install it from: https://docs.docker.com/engine/install/"
    exit 1
}

Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Building JARVIS image..."
docker compose build

Write-Host ""
Write-Host "Starting services (Ollama + JARVIS)..."
Write-Host "  - Ollama will pull the model on first run"
Write-Host "  - JARVIS will auto-connect to Ollama"
Write-Host ""
docker compose up -d

Write-Host ""
Write-Host "=== Done ==="
Write-Host "View logs: docker compose logs -f"
Write-Host "Stop:      docker compose down"
