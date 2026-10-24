@echo off
setlocal
cd /d "%~dp0"
if exist "dist\Tutuy MP3\Tutuy MP3.exe" (
    start "" "dist\Tutuy MP3\Tutuy MP3.exe"
    exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "app.py"
    exit /b
)
echo Ejecuta primero los pasos de instalacion indicados en README.md.
pause
