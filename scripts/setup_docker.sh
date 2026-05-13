#!/bin/bash
set -e

echo "=== JARVIS Docker Setup ==="

if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed."
    echo "Install it first: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "ERROR: Docker Compose is not installed."
    echo "Install it first: https://docs.docker.com/compose/install/"
    exit 1
fi

cd "$(dirname "$0")/.."

echo "Building JARVIS image..."
docker compose build

echo ""
echo "Starting services (Ollama + JARVIS)..."
echo "  - Ollama will pull the model on first run"
echo "  - JARVIS will auto-connect to Ollama"
echo ""
docker compose up -d

echo ""
echo "=== Done ==="
echo "View logs: docker compose logs -f"
echo "Stop:      docker compose down"
