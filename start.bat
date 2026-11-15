@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CipherPulse launcher
echo.
echo  ============================================
echo    CipherPulse - one click start
echo  ============================================
echo.

rem ---- 1. find a working Python -------------------------------------------
set "PYEXE="
set "PYARGS="
py -3 --version >nul 2>nul && (set "PYEXE=py" & set "PYARGS=-3")
if not defined PYEXE (
  python --version >nul 2>nul && set "PYEXE=python"
)
if not defined PYEXE (
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PYEXE (
  if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python311\python.exe"
)
if not defined PYEXE (
  echo Python was not found. Installing Python 3.12 with winget ^(about 1 minute^)...
  winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PYEXE (
  echo.
  echo Could not find or install Python automatically.
  echo Install it from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
  echo then double-click start.bat again.
  pause
  exit /b 1
)
echo Using Python: %PYEXE% %PYARGS%

rem ---- 2. virtual environment ---------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  "%PYEXE%" %PYARGS% -m venv .venv
  if errorlevel 1 ( echo Failed to create the virtual environment. & pause & exit /b 1 )
)

rem ---- 3. settings file ---------------------------------------------------
if not exist ".env" copy /y ".env.example" ".env" >nul

rem ---- 4. dependencies (only the first time) ------------------------------
if not exist ".venv\.deps_v4" (
  echo Installing dependencies. The first run takes a few minutes...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 ( echo Dependency install failed. Check your internet connection and run start.bat again. & pause & exit /b 1 )
  echo ok> ".venv\.deps_v4"
)

rem ---- 5. run -------------------------------------------------------------
echo.
echo Starting CipherPulse. Your browser will open automatically.
echo Keep this window open. Close it to stop.
echo.
".venv\Scripts\python.exe" run.py
echo.
echo CipherPulse stopped.
pause
