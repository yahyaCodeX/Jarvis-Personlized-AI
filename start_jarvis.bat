@echo off
chcp 65001 >nul
title JARVIS - Personal AI Assistant
color 0A
cd /d "%~dp0"
echo.
echo  ===================================================
echo     JARVIS Personal AI - Gemini Live + Flutter HUD
echo  ===================================================
echo.

if not exist ".env" (
    echo  [!] .env not found. Copy .env.example to .env and add your GEMINI_API_KEY.
    pause
    exit /b 1
)
if not exist "profile.json" (
    echo  [!] profile.json not found - copy profile.example.json to profile.json.
    echo      Jarvis will still run, but checkout/weather use empty defaults.
    echo.
)

:: Optional: local Ollama (used by the assignment generator and ask_local_qwen)
where ollama >nul 2>&1
if not errorlevel 1 (
    curl -s -o nul http://localhost:11434 >nul 2>&1
    if errorlevel 1 (
        echo  [*] Starting Ollama in background...
        start /B "" ollama serve >nul 2>&1
    )
)

:: Launch the HUD (it retries the connection until the server below is up)
set "HUD=jarvis_ui\build\windows\x64\runner\Release\jarvis_ui.exe"
if not exist "%HUD%" set "HUD=jarvis_ui\build\windows\x64\runner\Debug\jarvis_ui.exe"
if exist "%HUD%" (
    echo  [*] Starting HUD...
    start "" "%HUD%"
) else (
    echo  [!] HUD not built yet. Build it once with:
    echo      cd jarvis_ui ^&^& flutter build windows
    echo      Starting the server without the HUD.
)

echo  [*] Starting Jarvis core server (Ctrl+C to stop)...
echo.
python jarvis_server.py

echo.
echo  [!] Jarvis has shut down.
pause
