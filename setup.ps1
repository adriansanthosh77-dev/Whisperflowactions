$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  JARVIS Setup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Virtual environment
Write-Host "[1/6] Creating virtualenv..." -ForegroundColor Yellow
python -m venv venv

Write-Host "[2/6] Installing Python dependencies..." -ForegroundColor Yellow
& .\venv\Scripts\pip.exe install --upgrade pip
& .\venv\Scripts\pip.exe install -r requirements.txt

# 2. npm for Electron HUD
Write-Host "[3/6] Installing Node.js dependencies (Electron HUD)..." -ForegroundColor Yellow
if (Get-Command "npm" -ErrorAction SilentlyContinue) {
    npm install --silent
}

# 3. Playwright for browser automation
Write-Host "[4/6] Installing Playwright Chromium..." -ForegroundColor Yellow
& .\venv\Scripts\python.exe -m playwright install chromium

# 4. Create models directory
Write-Host "[5/6] Setting up models directory..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "models" | Out-Null

# 5. Create .env from template
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:"
Write-Host "  - Run: .\venv\Scripts\python.exe core\orchestrator.py"
Write-Host "  - Or double-click: run_jarvis.bat"
Write-Host ""
Write-Host "What happens on first run:" -ForegroundColor Yellow
Write-Host "  - Silero VAD model downloads (~5 MB)"
Write-Host "  - Whisper STT model downloads (~150 MB)"
Write-Host "  - SqueezeNet vision model downloads (~5 MB)"
Write-Host "  - Setup wizard appears to configure AI models"
Write-Host ""
Write-Host "All models download automatically. No manual steps needed."
