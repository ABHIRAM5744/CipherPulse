@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Push CipherPulse to GitHub
echo.
echo  ============================================
echo    Push CipherPulse to GitHub
echo  ============================================
echo.
echo Before you start, create an EMPTY public repository on GitHub:
echo   1. Open https://github.com/new while signed in as ABHIRAM5744
echo   2. Name it cipherpulse, choose Public
echo   3. Do NOT tick README, .gitignore or license
echo   4. Click Create repository
echo.
pause

where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed. Installing it with winget...
  winget install -e --id Git.Git --silent --accept-package-agreements --accept-source-agreements
  echo.
  echo Git was installed. Close this window and double-click push_to_github.bat again.
  pause
  exit /b 0
)

rem ---- make sure secrets, the virtual environment and local data are never uploaded ----
for %%i in (.env keys.env data/ .venv/ __pycache__/ *.pyc .pytest_cache/) do (
  findstr /x /c:"%%i" .gitignore >nul 2>nul || echo %%i>>.gitignore
)

if not exist ".git" git init -b main
git config user.name >nul 2>nul || git config user.name "ABHIRAM5744"
git config user.email >nul 2>nul || git config user.email "ABHIRAM5744@users.noreply.github.com"

git add -A

rem ---- safety: refuse to upload secrets ----
git ls-files --error-unmatch keys.env >nul 2>nul && ( echo STOP: keys.env would be uploaded. Remove it from git and try again. & pause & exit /b 1 )
git ls-files --error-unmatch .env >nul 2>nul && ( echo STOP: .env would be uploaded. Remove it from git and try again. & pause & exit /b 1 )
if exist keys.env (
  for /f "usebackq tokens=1,* delims==" %%a in ("keys.env") do (
    if not "%%b"=="" (
      git grep --cached -I -F -q "%%b" && ( echo STOP: a secret key value was found inside a file that would be uploaded. Nothing was pushed. & pause & exit /b 1 )
    )
  )
)
echo Safety check passed: no keys will be uploaded.

git commit -m "CipherPulse: NASA Space Apps Challenge 2026" >nul 2>nul
git branch -M main
set "REPO="
set /p REPO=GitHub repository name [cipherpulse]: 
if "!REPO!"=="" set "REPO=cipherpulse"
git remote remove origin >nul 2>nul
git remote add origin https://github.com/ABHIRAM5744/!REPO!.git
echo.
echo Pushing. If a GitHub sign-in window appears, sign in and approve.
git push -u origin main
if errorlevel 1 (
  echo.
  echo The push failed. Check that the repository exists at https://github.com/ABHIRAM5744/!REPO! and is empty, then run this file again.
  pause
  exit /b 1
)
echo.
echo Done. Your project link is:
echo   https://github.com/ABHIRAM5744/!REPO!
echo Open it in a private browser window to confirm anyone can see it.
pause
