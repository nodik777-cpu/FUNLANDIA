@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo FUNLANDIA - DAHUA BRIDGE INSTALLER
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
        echo Please install Python 3 from python.org and run this file again.
        echo During installation, enable: Add Python to PATH
        pause
        exit /b 1
    )
)

echo Installing required package...
%PY% -m pip install --upgrade requests
if errorlevel 1 (
    echo.
    echo Installation failed.
    pause
    exit /b 1
)

echo.
echo Installation completed successfully.
echo.
pause
