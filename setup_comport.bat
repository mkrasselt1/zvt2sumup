@echo off
chcp 65001 >nul 2>&1
title Virtuellen COM-Port einrichten

:: Administrator-Rechte pruefen
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo   Dieses Skript benoetigt Administrator-Rechte!
    echo   Starte als Administrator neu...
    echo.
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
python "%~dp0setup_comport.py"
