@echo off
setlocal EnableDelayedExpansion
title Local Database QA System - Setup Wizard
color 0B

echo ===============================================================================
echo      LOCAL DATABASE QUESTION-ANSWERING SYSTEM - AUTOMATED SETUP
echo ===============================================================================
echo.

:: 1. Check Python installation
echo [*] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    color 0C
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python 3.10 or higher from https://www.python.org/
    echo Remember to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [+] Found Python %PYTHON_VER%

:: 2. Check Ollama installation
echo.
echo [*] Checking Ollama installation...
ollama --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Ollama CLI not detected on PATH.
    echo Make sure to install Ollama from https://ollama.ai/ to run local inference.
) else (
    echo [+] Ollama CLI detected.
)

:: 3. Setup Virtual Environment
echo.
echo [*] Setting up virtual environment (.venv)...
if not exist ".venv" (
    python -m venv .venv
    echo [+] Created virtual environment in .venv\
) else (
    echo [+] Existing .venv directory found.
)

:: 4. Activate Virtual Environment
call .venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    color 0C
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo [+] Virtual environment activated.

:: 5. Upgrade pip & Install Dependencies
echo.
echo [*] Installing production dependencies from requirements.txt...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    color 0C
    echo [ERROR] Dependency installation encountered issues.
    pause
    exit /b 1
)

:: 6. Initialize Database & Seed Demo Accounts
echo.
echo [*] Initializing database and default persona accounts...
python -c "from src.auth import init_auth_db; init_auth_db()"
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Database init reported an error. It will retry automatically on app start.
) else (
    echo [+] Database initialized and demo accounts verified.
)

:: 7. Pull Default Ollama Model if Ollama is running
echo.
echo [*] Checking Ollama default model (qwen2.5-coder:latest)...
ollama list 2>nul | findstr /i "qwen2.5-coder" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [+] Model 'qwen2.5-coder' is already downloaded in Ollama.
) else (
    echo [INFO] You can pull the recommended model by running:
    echo        ollama pull qwen2.5-coder:latest
)

echo.
echo ===============================================================================
echo   SETUP COMPLETED SUCCESSFULLY!
echo ===============================================================================
echo.
echo  Default Persona Accounts Ready:
echo    - Student:               stu001 / Password@123 (Student ID: STU001)
echo    - Placement Coordinator: admin / admin123
echo    - Developer:             dev_admin / DeveloperPass@1234
echo.
echo  To start the application:
echo    Option A (One-Click):    Double-click 'run.bat'
echo    Option B (Terminal):     run.bat  OR  python run_production.py
echo.
pause
