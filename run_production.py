#!/usr/bin/env python3
"""
Production WSGI Entrypoint for Local Database QA System.
Runs a robust, multithreaded Waitress server suitable for Windows, Linux, and macOS.

Usage:
    python run_production.py
"""

import os
import sys
from pathlib import Path

# Ensure application root directory is on Python path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from app import app
from waitress import serve


def main():
    port = int(os.environ.get("PORT", 5000))
    threads = int(os.environ.get("WAITRESS_THREADS", 8))

    print("\n" + "=" * 75)
    print("  LOCAL DATABASE QA SYSTEM — PRODUCTION SERVER (WAITRESS WSGI)")
    print(f"  Access URL:       http://127.0.0.1:{port}")
    print(f"  Network Address:  http://0.0.0.0:{port}")
    print(f"  Worker Threads:   {threads}")
    print("  Press Ctrl+C to stop the server.")
    print("=" * 75 + "\n")

    serve(app, host='0.0.0.0', port=port, threads=threads)


if __name__ == '__main__':
    main()
