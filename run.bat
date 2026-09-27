@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python gui_app.py
if errorlevel 1 (
    echo.
    echo The application closed with an error. See the messages above.
    pause
)
