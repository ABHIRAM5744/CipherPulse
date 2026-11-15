@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo Run start.bat once first to set up. & pause & exit /b 1 )
".venv\Scripts\python.exe" scripts\setup_keys.py
echo.
pause
