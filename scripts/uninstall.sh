#!/usr/bin/env bash
# Uninstall Feederr service and remove files (Linux/macOS)

cd "$(dirname "$0")/.."

if [ -f feederr.pid ]; then
    PID=$(cat feederr.pid)
    echo "Stopping Feederr (PID: $PID)"
    kill $PID && rm feederr.pid
else
    echo "Feederr service not running (no feederr.pid)"
fi

read -p "Delete all Feederr files (except scripts/)? [y/N]: " confirm
if [[ $confirm =~ ^[Yy]$ ]]; then
    rm -rf venv data logs cookies config app feederr.pid
    echo "Feederr files removed."
else
    echo "Uninstall cancelled."
fi
