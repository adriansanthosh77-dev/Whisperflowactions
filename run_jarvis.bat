@echo off
setlocal

echo Checking requirements...

:: 1. Check Whisper
if not exist "whisper-cli.exe" (
    echo ERROR: whisper-cli.exe missing!
    echo Please ensure whisper-cli.exe is in this folder.
    pause
    exit /b
)

:: 2. Check Virtual Environment
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please run setup.ps1 first.
    pause
    exit /b
)

:: 3. Ask about Obscura
set /p use_obscura="Use Obscura Stealth Engine? (y/N): "
if /i "%use_obscura%"=="y" (
    echo Starting Obscura Stealth Engine...
    start /b "" "obscura.exe" serve --port 9222 --stealth
    set USE_OBSCURA=true
) else (
    set USE_OBSCURA=false
)

echo Launching JARVIS...
venv\Scripts\python.exe core\orchestrator.py

pause
