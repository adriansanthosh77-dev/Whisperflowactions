$ErrorActionPreference = "Stop"

Write-Host "==> Creating virtualenv..."
py -3 -m venv venv

Write-Host "==> Activating virtualenv..."
& .\venv\Scripts\Activate.ps1

Write-Host "==> Installing Python deps..."
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "==> Installing Playwright Chromium..."
python -m playwright install chromium

Write-Host "==> Checking Whisper model folder..."
New-Item -ItemType Directory -Force -Path models | Out-Null
if (-not (Test-Path "models\ggml-base.en.bin")) {
    Write-Host "Whisper model is missing: models\ggml-base.en.bin"
    Write-Host "Download it from:"
    Write-Host "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Add your OPENAI_API_KEY before running."
}

Write-Host "==> Setup complete."
Write-Host "Run with: python core\orchestrator.py"
