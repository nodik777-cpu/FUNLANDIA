@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo FUNLANDIA - DAHUA BRIDGE
echo ========================================
echo.

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PY=python"
    ) else (
        echo Python is not installed.
        echo Run INSTALL_DAHUA_BRIDGE.BAT first.
        pause
        exit /b 1
    )
)

set "DAHUA_HOST=192.168.1.202"
set "DAHUA_USER=admin"
set "STAFF_WEBHOOK=https://worker-production-a2c3.up.railway.app/dahua"
set "POLL_SECONDS=20"

echo Checking access to Dahua %DAHUA_HOST% ...
%PY% -c "import requests; r=requests.get('http://%DAHUA_HOST%/cgi-bin/magicBox.cgi?action=getSystemInfo',timeout=5); print('Dahua HTTP OK:', r.status_code)" 2>nul
if errorlevel 1 (
    echo WARNING: Windows cannot reach Dahua over HTTP.
    echo Make sure this computer is connected to the same local network as the Dahua terminal.
    pause
    exit /b 1
)

echo Dahua is reachable over HTTP.
echo Starting bridge. Keep this window open.
echo Password input will be hidden.
echo Press Ctrl+C to stop.
echo.
%PY% dahua_bridge.py

pause
