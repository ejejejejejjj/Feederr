@echo off
setlocal enabledelayedexpansion
REM Feederr Launch Script for Windows

cd /d %~dp0..

REM Check if venv exists
if not exist "venv" (
    echo Virtual environment not found. Run scripts\setup.bat first.
    pause
    exit /b 1
)

REM Activate venv
call venv\Scripts\activate.bat

REM Create directories if missing
if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "cookies" mkdir cookies
if not exist "config" mkdir config

REM Load .env if present
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "line=%%a"
        if not "!line:~0,1!"=="#" (
            if not "%%a"=="" set "%%a=%%b"
        )
    )
)

REM Default port (fallback if not in .env)
if "%PORT%"=="" set PORT=9797
if "%HOST%"=="" set HOST=0.0.0.0

echo ============================================
echo   Starting Feederr on %HOST%:%PORT%
echo ============================================
echo.

REM Start the application in background as a service
start /b uvicorn app.main:app --host %HOST% --port %PORT% > logs\feederr.log 2>&1
echo Feederr started as background service.
