$ErrorActionPreference = 'SilentlyContinue'
$desktop = [Environment]::GetFolderPath('Desktop')
$out = Join-Path $desktop 'DeepSeek report'
New-Item -ItemType Directory -Force -Path $out | Out-Null

$lines = @()
$lines += '===== DeepSeek Balance Monitor - Diagnostic Report ====='
$lines += 'Generated: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
$lines += ''
$lines += '----- System -----'
$lines += ('OS Name: ' + (Get-CimInstance Win32_OperatingSystem).Caption)
$lines += ('OS Version: ' + (cmd /c ver 2>&1 | Out-String).Trim())
$lines += ('Is 64-bit: ' + [Environment]::Is64BitOperatingSystem)
$lines += ('Memory (GB): ' + [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1))
$lines += ''
$lines += '----- WebView2 Runtime -----'
$found = $false
foreach ($p in @(
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
  'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
)) {
  $v = (Get-ItemProperty -Path $p -Name pv).pv
  if ($v) { $found = $true; $lines += ('Installed, version: ' + $v) }
}
if (-not $found) { $lines += 'NOT FOUND (this is the most likely reason the app fails)' }
$lines += ''
$lines += '----- Microsoft Edge -----'
if (Test-Path 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') { $lines += 'Edge installed' }
elseif (Test-Path 'C:\Program Files\Microsoft\Edge\Application\msedge.exe') { $lines += 'Edge installed' }
else { $lines += 'Edge NOT found' }
$lines += ''
$lines += '----- Please also answer (write below) -----'
$lines += '1) What did run.bat show on screen? Any red/error text?'
$lines += '2) After starting the app: is there a tray icon? What happens on click / right-click?'
$lines += '3) Did antivirus block it? If yes, what did it say?'
$lines += ''

$infoPath = Join-Path $out 'SystemInfo.txt'
[System.IO.File]::WriteAllLines($infoPath, $lines, (New-Object System.Text.UTF8Encoding($true)))

$logSrc = Join-Path $env:APPDATA 'DeepSeekBalanceMonitor\debug.log'
if (Test-Path $logSrc) {
  Copy-Item $logSrc (Join-Path $out 'debug.log') -Force
  Write-Host ('Found app log: ' + $logSrc)
} else {
  Write-Host 'App log not found (app may never have started far enough to write it).'
  [System.IO.File]::WriteAllText((Join-Path $out 'NO debug.log.txt'), 'debug.log was not found.', (New-Object System.Text.UTF8Encoding($true)))
}
Write-Host ('Report saved to: ' + $out)