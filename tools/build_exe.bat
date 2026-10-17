@echo off
cd /d "%~dp0.."
if not exist icon.ico ".venv\Scripts\python.exe" tools\make_icon.py
"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /codepage:65001 /target:winexe /optimize+ /win32icon:icon.ico /r:System.Windows.Forms.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /out:"VRChat Translator.exe" tools\launcher.cs
if errorlevel 1 (
  echo Build FAILED
  pause
  exit /b 1
)
echo Built: VRChat Translator.exe
