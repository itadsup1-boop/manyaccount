@echo off
setlocal
cd /d "%~dp0\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_windows.ps1" %*
if errorlevel 1 (
  echo.
  echo Ung dung ket thuc voi loi. Kiem tra thong bao o tren.
  pause
  exit /b 1
)
