@echo off
title JARVIS - Just A Rather Very Intelligent System
cd /d "%~dp0"

mode con: cols=72 lines=20

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
echo [....] (This takes 5-15 seconds to load models)
echo.
set KMP_DUPLICATE_LIB_OK=TRUE

:: Launch and show live logs
venv\Scripts\python.exe core\orchestrator.py 2>&1

:: If we get here, orchestrator exited
echo.
echo JARVIS has shut down.
pause
