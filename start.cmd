@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SongUp Queue v2

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python not found. Install Python 3.9+ and tick "Add to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] First run: creating venv and installing Flask ...
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] dependency install failed, check your network.
    pause
    exit /b 1
  )
)

echo [2/2] Starting. Two addresses will be printed below:
echo        - HOST  page : open in a browser, fullscreen it on the TV
echo        - GUEST page : send to the group chat / turn into a QR code
echo        Close this window to stop the server.
echo.
".venv\Scripts\python.exe" app.py
pause
