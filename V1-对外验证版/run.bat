@echo off
cd /d "%~dp0"
echo ============================================
echo   DeepSeek Balance Monitor - V1 Check
echo ============================================
echo.
echo [1/2] Checking WebView2 Runtime...
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1
if %errorlevel%==0 goto found
reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1
if %errorlevel%==0 goto found
echo      WebView2 Runtime NOT found.
echo      Trying to download and install it (need internet, 1-2 min)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%TEMP%\webview2boot.exe'; try { Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $p -UseBasicParsing -TimeoutSec 120; Start-Process -FilePath $p -ArgumentList '/silent /install' -Wait; Write-Host 'Installed. Please run this script again.' } catch { Write-Host 'Download failed. Please check network, or install WebView2 Runtime manually.' }"
echo.
echo Press any key to continue...
pause >nul
exit /b
:found
echo      WebView2 Runtime OK.
echo.
echo [2/2] Starting the app...
start "" "%~dp0DeepSeekBalanceMonitor-v1.0.exe"
echo If the window does not appear, see "Troubleshooting.txt".
echo.
echo Press any key to continue...
pause >nul