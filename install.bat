@echo off
setlocal EnableDelayedExpansion
title Power Profiler Setup & Installer
color 0A

echo ==============================================================================
echo           UNIVERSAL POWER PROFILER & DUAL WATTMETER INSTALLER
echo           Web IDE (Arduino Cloud Style) + Desktop GUI Environment
echo ==============================================================================
echo.

:: 1. Check Python installation
echo [*] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found on your system PATH!
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do echo [OK] Found: %%i
echo.

:: 2. Upgrade pip
echo [*] Ensuring pip is up to date...
python -m pip install --upgrade pip --quiet

:: 3. Install dependencies from requirements.txt
echo [*] Installing required Python dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Standard install had warnings, attempting user-level install...
    python -m pip install --user -r requirements.txt
)

echo.
echo [OK] All dependencies successfully verified!
echo.

:: 4. Create Desktop Shortcuts using PowerShell
echo [*] Creating Desktop shortcuts for 1-click launch...
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$s1 = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\PowerProfilerWeb.lnk'); " ^
    "$s1.TargetPath = '%SCRIPT_DIR%\Launch-Web-IDE.bat'; " ^
    "$s1.WorkingDirectory = '%SCRIPT_DIR%'; " ^
    "$s1.Description = 'Universal Power Profiler Web IDE (Arduino Cloud Style)'; " ^
    "$s1.Save(); " ^
    "$s2 = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\PowerProfilerDesktop.lnk'); " ^
    "$s2.TargetPath = '%SCRIPT_DIR%\Launch-Desktop-GUI.bat'; " ^
    "$s2.WorkingDirectory = '%SCRIPT_DIR%'; " ^
    "$s2.Description = 'Universal Power Profiler Desktop GUI'; " ^
    "$s2.Save();"

echo [OK] Shortcuts created on Desktop:
echo      - PowerProfilerWeb.lnk (Browser Web IDE)
echo      - PowerProfilerDesktop.lnk (Desktop GUI)
echo.
echo ==============================================================================
echo   INSTALLATION COMPLETE!
echo   You can now launch the application using:
echo     1. Launch-Web-IDE.bat        (Runs in web browser @ http://localhost:8000)
echo     2. Launch-Desktop-GUI.bat    (Runs as a native desktop window)
echo ==============================================================================
echo.
pause
