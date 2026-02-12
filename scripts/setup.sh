#!/usr/bin/env bash
# Feederr Setup Script for Linux/macOS
# Creates virtual environment, installs dependencies, and Playwright browsers

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "============================================"
echo "  Feederr Setup"
echo "============================================"
echo ""

# Check Python version
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python 3.11+ is required but not found."
    echo "Install it from https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$($PYTHON -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PYTHON -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]); then
    echo "ERROR: Python 3.11+ is required. Found Python $PY_VERSION"
    exit 1
fi

echo "[1/5] Python $PY_VERSION detected"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "[2/5] Creating virtual environment..."
    $PYTHON -m venv venv
fi

# Activate venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

echo "[3/5] Installing dependencies..."
pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
python -m playwright install chromium

echo "[4/5] Setup complete."
echo "[5/5] You can now run scripts/launch.sh"
