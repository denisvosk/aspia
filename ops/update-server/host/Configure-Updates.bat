@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Configure-Updates.ps1"
set "result=%errorlevel%"
echo.
pause
exit /b %result%
