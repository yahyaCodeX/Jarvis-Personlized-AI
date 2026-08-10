@echo off
title JARVIS — Personal AI Assistant
color 0A
cls
echo.
echo  ╔═══════════════════════════════════════════════════╗
echo  ║   🤖  JARVIS Personal AI — Muhammad Yahya        ║
echo  ╚═══════════════════════════════════════════════════╝
echo.

:: Check if Ollama is already running
curl -s -o nul -w "%%{http_code}" http://localhost:11434 2^>nul | findstr "200" >nul 2>&1
if errorlevel 1 (
    echo  [*] Starting Ollama in background...
    start /B "" ollama serve
    timeout /t 4 /nobreak >nul
    echo  [OK] Ollama started.
) else (
    echo  [OK] Ollama is already running.
)

echo  [*] Launching Jarvis...
echo.
python "%~dp0brain.py"

echo.
echo  [!] Jarvis has shut down.
pause
