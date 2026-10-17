@echo off
rem Makes a clean zip for sharing: NO config.json (your API keys), NO usage.json, NO app.log, NO .venv.
rem The friend runs "VRChat Translator.exe" - it offers to install everything and asks for nothing of yours.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_share.ps1"
if errorlevel 1 (
  echo FAILED
  pause
  exit /b 1
)
pause
