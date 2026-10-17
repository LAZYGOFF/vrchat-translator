@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_share.ps1"
if errorlevel 1 (
  echo FAILED
  pause
  exit /b 1
)
pause
