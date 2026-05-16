@echo off
title JARVIS - Just A Rather Very Intelligent System
cd /d "%~dp0"

mode con: cols=72 lines=40
powershell -NoProfile -Command "[console]::BufferWidth=72; [console]::BufferHeight=9999; [console]::WindowHeight=40" 2>nul

echo ==================================================================
echo         JARVIS - Just A Rather Very Intelligent System
echo ==================================================================
echo.

:: Kill any leftover Electron HUD from previous run
taskkill /f /fi "WINDOWTITLE eq JARVIS*" /im electron.exe >nul 2>&1

:: Check venv
if not exist "venv\Scripts\python.exe" (
    echo [FAIL] Virtual environment not found.
    echo        Run setup.ps1 first.
    pause
    exit /b 1
)

:: Check .env
if not exist ".env" (
    echo [....] Creating .env from template...
    copy .env.example .env >nul
)

:: Warn about Ollama
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Ollama not found — JARVIS will use browser-based LLM
    echo        if LLM_PROVIDER=browser is set in .env
    echo.
)

echo [....] Starting JARVIS...
echo [....] (Takes ~30-45 seconds to load models)
echo.

:: Launch and show live logs (also write to file for review)
if not exist "logs" mkdir "logs"
powershell -NoProfile -Command "$env:KMP_DUPLICATE_LIB_OK='TRUE'; .\venv\Scripts\python.exe core\orchestrator.py 2>&1 | Tee-Object -FilePath 'logs/latest_session.log'"

:: If we get here, orchestrator exited
echo.
echo JARVIS has shut down.
pause
