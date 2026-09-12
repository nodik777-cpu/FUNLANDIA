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

set /p DAHUA_PASSWORD=Enter Dahua admin password: 
if "%DAHUA_PASSWORD%"=="" (
    echo Password cannot be empty.
    pause
    exit /b 1
)

set "DAHUA_HOST=192.168.1.202"
set "DAHUA_USER=admin"
set "STAFF_WEBHOOK=https://worker-production-a2c3.up.railway.app/dahua"
set "POLL_SECONDS=20"

echo.
echo Testing connection to Dahua %DAHUA_HOST% ...
ping -n 1 -w 1500 %DAHUA_HOST% >nul
if errorlevel 1 (
    echo WARNING: Dahua did not answer ping.
    echo Make sure this computer is connected to the Funlandia local network.
    pause
    exit /b 1
)

echo Dahua is reachable.
echo Starting bridge. Keep this window open.
echo Press Ctrl+C to stop.
echo.
%PY% dahua_bridge.py

pause
