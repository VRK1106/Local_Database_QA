@echo off
title Cloudflare Tunnel - Local Database QA
echo ===================================================
echo   Starting Cloudflare Quick Tunnel for Port 5000
echo ===================================================
echo.
echo Make sure your app is running (python app.py or run.bat)!
echo Starting tunnel...
echo.
cloudflared tunnel --url http://127.0.0.1:5000
pause
