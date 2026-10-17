@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_share_exe.ps1"
if errorlevel 1 (
  echo FAILED
  pause
  exit /b 1
)
pause
