# run_jarvis.ps1

Write-Host "Checking requirements..." -ForegroundColor Cyan

if ($args -contains "--doctor") {
    $env:KMP_DUPLICATE_LIB_OK = "TRUE"
    & .\venv\Scripts\python.exe -m core.doctor
    exit $LASTEXITCODE
}

# 1. Check Whisper
if (-not (Test-Path "whisper-cli.exe")) {
    Write-Host "ERROR: whisper-cli.exe missing!" -ForegroundColor Red
    Write-Host "Please extract whisper-cli.exe from the zip into this folder."
    exit
}

# 2. Check Ollama
$ollamaCheck = Get-Process ollama -ErrorAction SilentlyContinue
if (-not $ollamaCheck) {
    Write-Host "WARNING: Ollama is not running." -ForegroundColor Yellow
    Write-Host "Please start Ollama from your Start menu."
    # We don't exit here as it might be in the PATH but just not running
}

# 3. Ask about Obscura
Write-Host "TIP: Choose 'n' to use your real browser (Brave/Chrome/Edge) with a UI." -ForegroundColor Gray
$useObscura = Read-Host "Use Obscura Stealth Engine? (Headless/No-UI) (y/N)"
if ($useObscura -eq "y") {
    Write-Host "Starting Obscura Stealth Engine..." -ForegroundColor Green
    Start-Process ".\obscura.exe" -ArgumentList "serve --port 9222 --stealth" -NoNewWindow
    # Update .env temporarily or just set env var
    $env:USE_OBSCURA = "true"
} else {
    $env:USE_OBSCURA = "false"
}

# 4. Run JARVIS
Write-Host "Launching JARVIS..." -ForegroundColor Cyan
$env:KMP_DUPLICATE_LIB_OK = "TRUE"
& .\venv\Scripts\python.exe core\orchestrator.py
