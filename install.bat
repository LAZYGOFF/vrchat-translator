@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto deps

set "PY="
for %%V in (3.12 3.13 3.11 3.10 3.14) do (
  if not defined PY py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
)
if not defined PY python -c "import sys; sys.exit(not (3,10) <= sys.version_info[:2] <= (3,14))" >nul 2>nul && set "PY=python"
set "LOCALPY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LOCALPY%" set PY="%LOCALPY%"
if defined PY goto venv

echo Python not found - downloading Python 3.12 from python.org (26 MB)...
set "PYSETUP=%TEMP%\python-3.12.10-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $env:PYSETUP"
if not exist "%PYSETUP%" (
  echo Download FAILED. Check the internet connection and try again.
  pause
  exit /b 1
)
echo Installing Python 3.12 for this user only (no admin rights needed)...
"%PYSETUP%" /quiet InstallAllUsers=0 PrependPath=0 Include_test=0 Include_launcher=0 Shortcuts=0
del "%PYSETUP%" >nul 2>nul
if not exist "%LOCALPY%" (
  echo Python install FAILED. Install Python 3.12 from python.org yourself and run this again.
  pause
  exit /b 1
)
set PY="%LOCALPY%"

:venv
echo Creating virtual environment with: %PY%
%PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo Could not create .venv
  pause
  exit /b 1
)

:deps
echo Downloading components (about 3 GB, 5-15 minutes)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Install FAILED - see errors above.
  pause
  exit /b 1
)
echo.
echo Done! Press any key - the translator will start.
pause >nul