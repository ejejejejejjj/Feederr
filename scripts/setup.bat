@echo off
REM Feederr Setup Script for Windows
REM Creates virtual environment, installs dependencies, and Playwright browsers

echo ============================================
echo   Feederr Setup
echo ============================================
echo.

cd /d %~dp0..

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python 3.11+ is required but not found.
    echo Install it from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=*" %%i in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VERSION=%%i
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.version_info.major)"') do set PY_MAJOR=%%i
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.version_info.minor)"') do set PY_MINOR=%%i

if %PY_MAJOR% lss 3 (
    echo ERROR: Python 3.11+ is required. Found Python %PY_VERSION%
    pause
    exit /b 1
)
if %PY_MAJOR% equ 3 if %PY_MINOR% lss 11 (
    echo ERROR: Python 3.11+ is required. Found Python %PY_VERSION%
    pause
    exit /b 1
)

echo [1/5] Python %PY_VERSION% detected

REM Create virtual environment
if not exist "venv" (
    echo [2/5] Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

echo [3/5] Installing dependencies...
pip install --no-cache-dir -r requirements.txt

REM Install Playwright browsers
python -m playwright install chromium

echo [4/5] Setup complete.
echo [5/5] You can now run scripts\launch.bat
