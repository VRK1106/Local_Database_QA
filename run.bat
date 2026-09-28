@echo off
setlocal
title Local Database QA System Launcher
color 0A

echo ===============================================================================
echo     LOCAL DATABASE QUESTION-ANSWERING SYSTEM (OLLAMA + CHROMADB + RBAC)
echo ===============================================================================
echo.

:: Activate virtual environment if present
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [+] Using virtual environment: .venv\
) else (
    echo [INFO] Virtual environment not found; using global Python interpreter.
)

:: Set PYTHONPATH to project root
set PYTHONPATH=.

:: Launch application
echo [*] Starting Local Database QA System...
echo [*] Open your web browser at: http://127.0.0.1:5000
echo.
python app.py

pause
