@echo off
cd /d "%~dp0"
title LPR System Setup
echo ====================================================
echo    Setting up License Plate Recognition System
echo ====================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on this system.
    echo Please install Python 3.10 or newer from https://www.python.org/downloads/
    echo During installation, make sure to check "Add Python to PATH".
    echo Then run this file again.
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create the virtual environment.
    pause
    exit /b 1
)

echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3/4] Installing required packages, this may take a few minutes...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install one or more packages. See the messages above.
    pause
    exit /b 1
)

echo [4/4] Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_shortcut.ps1"

echo.
echo ====================================================
echo Setup finished successfully.
echo You can now start the program from the desktop shortcut,
echo or by double-clicking run.bat in this folder.
echo ====================================================
pause
