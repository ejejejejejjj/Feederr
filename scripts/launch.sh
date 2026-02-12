#!/usr/bin/env bash
# Feederr Launch Script for Linux/macOS

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Run ./scripts/setup.sh first."
    exit 1
fi

# Activate venv
source venv/bin/activate

# Create directories if missing
mkdir -p data logs cookies config

# Load .env if present
if [ -f ".env" ]; then
    set -a
    source ".env"
    set +a
fi

# Defaults (fallback if not in .env)
PORT=${PORT:-9797}
HOST=${HOST:-0.0.0.0}

echo "============================================"
echo "  Starting Feederr on ${HOST}:${PORT}"
echo "============================================"
echo ""

# Start the application in background as a service
nohup uvicorn app.main:app --host "$HOST" --port "$PORT" > logs/feederr.log 2>&1 &
echo $! > feederr.pid
echo "Feederr started as background service (PID: $(cat feederr.pid))"
