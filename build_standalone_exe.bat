@echo off
REM Run this file on Windows itself (not Linux/Mac) - PyInstaller only
REM builds an executable for the same OS it runs on.
cd /d "%~dp0"

call venv\Scripts\activate.bat
pip install pyinstaller

echo Pre-downloading OCR models for fully offline use...
python download_models.py

echo Pre-downloading object-detection model for line/zone crossing alerts...
python download_yolo_model.py

set "ICON_OPT="
if exist "app_icon.ico" set "ICON_OPT=--icon app_icon.ico"

echo Building standalone executable, this may take a few minutes...
pyinstaller --noconfirm --onefile --windowed --name LPR-Camera-System %ICON_OPT% gui_app.py

echo.
echo Done. The executable is at: dist\LPR-Camera-System.exe
echo IMPORTANT: also copy the "easyocr_models" folder next to that exe
echo (or use installer.iss, which bundles it automatically) so the app
echo works fully offline, even on the very first run.
pause
