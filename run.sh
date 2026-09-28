#!/usr/bin/env bash
# ==============================================================================
# Local Database QA System - Linux / macOS Launcher
# ==============================================================================
set -e

if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "[+] Using virtual environment: .venv"
fi

export PYTHONPATH=.
echo "[*] Starting Local Database QA System..."
echo "[*] Open your web browser at: http://127.0.0.1:5000"
echo ""
python3 app.py
