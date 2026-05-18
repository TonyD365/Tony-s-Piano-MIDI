@echo off
REM Starts midi_bridge.py and a cloudflared quick tunnel.
REM Usage: double-click or run from cmd.exe in this folder.

setlocal
set HERE=%~dp0
set VENV_PY=%HERE%.venv\Scripts\python.exe

if not exist "%VENV_PY%" (
    echo Python venv not found at %VENV_PY%
    echo Create with:  py -3 -m venv "%HERE%.venv" ^&^& "%HERE%.venv\Scripts\pip" install -r "%HERE%requirements.txt"
    pause
    exit /b 1
)

where cloudflared >nul 2>&1
if errorlevel 1 (
    echo cloudflared not found on PATH. Download it from
    echo   https://github.com/cloudflare/cloudflared/releases
    echo and place cloudflared.exe somewhere on PATH.
    pause
    exit /b 1
)

echo [run] starting midi_bridge.py...
start "midi_bridge" /B "%VENV_PY%" "%HERE%midi_bridge.py"

timeout /t 2 /nobreak >nul

echo [run] starting cloudflared quick tunnel...
set TUNNEL_LOG=%TEMP%\cloudflared_tunnel.log
start "cloudflared" /B cmd /c cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8080 ^> "%TUNNEL_LOG%" 2^>^&1

echo [run] waiting for tunnel URL...
set URL=
for /l %%i in (1,1,60) do (
    if exist "%TUNNEL_LOG%" (
        for /f "delims=" %%a in ('findstr /r /c:"https://[A-Za-z0-9.-]*\.trycloudflare\.com" "%TUNNEL_LOG%"') do (
            for /f "tokens=*" %%b in ('echo %%a ^| findstr /r /c:"https://[A-Za-z0-9.-]*\.trycloudflare\.com"') do (
                set URL=%%b
                goto :found
            )
        )
    )
    timeout /t 1 /nobreak >nul
)

:found
if "%URL%"=="" (
    echo [run] FAILED to detect tunnel URL. See %TUNNEL_LOG%
    pause
    exit /b 1
)

echo.
echo ================================================================
echo   Tunnel URL: %URL%
echo   Run in Roblox chat:  /pianourl %URL%
echo ================================================================
echo %URL% | clip
echo [run] copied to clipboard.
echo.
echo Tailing tunnel log. Close this window to stop.
type "%TUNNEL_LOG%"
:loop
timeout /t 5 /nobreak >nul
type "%TUNNEL_LOG%"
goto loop
