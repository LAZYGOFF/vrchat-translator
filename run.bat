@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First start: installing dependencies, this takes a while...
  call "%~dp0install.bat"
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
