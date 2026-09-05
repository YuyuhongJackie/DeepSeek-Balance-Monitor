@echo off
cd /d "%~dp0"
echo ============================================
echo   Collect Diagnostic Report
echo ============================================
echo Collecting system info and app log...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0report.ps1"
echo.
echo Done! Report folder is on the Desktop.
echo Please zip folder "DeepSeek report" and send it back.
echo.
echo Press any key to continue...
pause >nul