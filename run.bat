@echo off
title Local Database Question-Answering System Launcher
color 0A
echo =========================================================================
echo    STARTING LOCAL DATABASE QUESTION-ANSWERING SYSTEM (OLLAMA + CHROMADB)
echo =========================================================================
echo.

set PYTHONPATH=.
python app.py

pause
