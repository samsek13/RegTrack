@echo off
REM RegTracker Web Interface Stop Script

echo Stopping RegTracker Web Interface...

REM Use PowerShell to find and kill process on port 5000
powershell -Command "Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"

echo Done.