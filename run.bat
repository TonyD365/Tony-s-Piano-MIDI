@echo off
REM Starts midi_bridge.py + cloudflared, prints + copies the tunnel URL.
REM All the heavy lifting is in launcher.py so this stays trivially simple.

setlocal
set HERE=%~dp0
set VENV_PY=%HERE%.venv\Scripts\python.exe

if exist "%VENV_PY%" (
    "%VENV_PY%" "%HERE%launcher.py"
) else (
    echo Python venv not found at %VENV_PY%
    echo Create it first:
    echo   py -3 -m venv "%HERE%.venv"
    echo   "%HERE%.venv\Scripts\pip" install -r "%HERE%requirements.txt"
    pause
    exit /b 1
)
