#!/bin/bash
set -e

echo "==> Creating virtualenv..."
python3 -m venv venv
source venv/bin/activate

echo "==> Installing Python deps..."
pip install -r requirements.txt

echo "==> Installing Playwright Chromium..."
playwright install chromium

echo "==> Installing Whisper.cpp binary..."
# Download whisper.cpp pre-built binary for your platform
# macOS (arm64):
# curl -L https://github.com/ggerganov/whisper.cpp/releases/latest/download/whisper-cpp-macos-arm64.tar.gz | tar xz -C /usr/local/bin/
# Linux (x86_64):
# curl -L https://github.com/ggerganov/whisper.cpp/releases/latest/download/whisper-cpp-linux-x86_64.tar.gz | tar xz -C /usr/local/bin/

# Download base.en model (142MB, fast, English)
mkdir -p models
if [ ! -f "models/ggml-base.en.bin" ]; then
  echo "==> Downloading Whisper base.en model..."
  curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin" \
    -o models/ggml-base.en.bin
fi

echo "==> Setup complete. Copy .env.example to .env and add your OPENAI_API_KEY"
