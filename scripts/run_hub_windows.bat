@echo off
setlocal
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_hub_windows.ps1" %*
if errorlevel 1 (
  echo.
  echo Web Hub khong khoi dong duoc. Xem data\logs\hub_backend_error.log va hub_frontend_error.log.
  pause
  exit /b 1
)
