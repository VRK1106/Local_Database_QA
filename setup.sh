#!/usr/bin/env bash
# ==============================================================================
# Local Database QA System - Automated Linux / macOS Setup Script
# ==============================================================================
set -e

echo "==============================================================================="
echo "     LOCAL DATABASE QUESTION-ANSWERING SYSTEM - AUTOMATED SETUP"
echo "==============================================================================="
echo ""

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "[-] Error: python3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi
echo "[+] Found Python $(python3 --version)"

# 2. Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "[!] Warning: ollama CLI not detected on PATH. Install from https://ollama.ai/"
else
    echo "[+] Ollama detected."
fi

# 3. Virtual Environment
if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv .venv
fi

# 4. Activate
source .venv/bin/activate
echo "[+] Virtual environment activated."

# 5. Install Dependencies
echo "[*] Installing dependencies from requirements.txt..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 6. Initialize Database
echo "[*] Initializing database and default demo accounts..."
python -c "from src.auth import init_auth_db; init_auth_db()"

echo ""
echo "==============================================================================="
echo "  SETUP COMPLETED SUCCESSFULLY!"
echo "==============================================================================="
echo ""
echo "Default Accounts:"
echo "  - Student:               stu001 / Password@123 (Student ID: STU001)"
echo "  - Placement Coordinator: admin / admin123"
echo "  - Developer:             dev_admin / DeveloperPass@1234"
echo ""
echo "To start the application:"
echo "  ./run.sh   OR   python run_production.py"
echo ""
