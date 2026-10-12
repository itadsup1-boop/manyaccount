@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download_whisper_model.ps1" %*
if errorlevel 1 (
  echo Tai Whisper that bai.
  exit /b 1
)
pause
