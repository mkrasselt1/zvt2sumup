@echo off
chcp 65001 >nul 2>&1
title ZVT-zu-SumUp Gateway - Einrichtung
cd /d "%~dp0"

echo Starte Einrichtungsassistenten...
python -m gateway.gui_setup
if %ERRORLEVEL% neq 0 (
    echo.
    echo Fehler beim Starten des Assistenten.
    echo Haben Sie install.bat bereits ausgefuehrt?
    echo.
    pause
)
