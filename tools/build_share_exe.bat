@echo off
rem One-file build for a friend: ..\VRChat Translator Setup.exe (no API keys, no settings inside).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_share_exe.ps1"
if errorlevel 1 (
  echo FAILED
  pause
  exit /b 1
)
pause
