@echo off
setlocal
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1" %*
if errorlevel 1 (
  echo.
  echo Setup that bai. Kiem tra thong bao o tren.
  pause
  exit /b 1
)
pause
