@echo off
REM Uninstall Feederr service and remove files (Windows)
cd /d %~dp0..

if exist feederr.pid (
    set /p PID=<feederr.pid
    echo Stopping Feederr (PID: %PID%)
    taskkill /PID %PID% /F
    del feederr.pid
) else (
    echo Feederr service not running (no feederr.pid)
)

set /p confirm=Delete all Feederr files (except scripts/)? [y/N]: 
if /i "%confirm%"=="y" (
    rmdir /s /q venv
    rmdir /s /q data
    rmdir /s /q logs
    rmdir /s /q cookies
    rmdir /s /q config
    rmdir /s /q app
    del feederr.pid
    echo Feederr files removed.
) else (
    echo Uninstall cancelled.
)
