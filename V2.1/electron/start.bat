@echo off
rem DeepSeek Balance Monitor - Electron dev start
cd /d "%~dp0"
set "PATH=%~dp0..\.nodejs\node-v22.23.2-win-x64;%PATH%"
call npm start
if errorlevel 1 (
  echo.
  echo npm start failed. See messages above.
  echo Press any key to continue...
  pause >nul
)