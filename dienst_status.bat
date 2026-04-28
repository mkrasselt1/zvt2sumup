@echo off
chcp 65001 >nul 2>&1
title ZVT-zu-SumUp Gateway - Dienst-Status
cd /d "%~dp0"

echo.
python -m gateway.win_service status
echo.
pause
