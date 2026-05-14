#!/bin/bash
set -e

echo "========================================"
echo "  JARVIS Setup Script"
echo "========================================"
echo ""

echo "[1/4] Creating virtualenv..."
python3 -m venv venv
source venv/bin/activate

echo "[2/4] Installing Python dependencies..."
pip install -r requirements.txt

echo "[3/4] Installing Playwright Chromium..."
playwright install chromium

echo "[4/4] Setting up models directory..."
mkdir -p models

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  - Run: venv/bin/python core/orchestrator.py"
echo ""
echo "All models download automatically on first run."
