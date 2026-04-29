@echo off
chcp 65001 >nul 2>&1
title ZVT/SumUp Test-Tool
echo.
echo  ZVT/SumUp Test-Tool wird gestartet...
echo.
python "%~dp0test_tool.py" %*
if errorlevel 1 (
    echo.
    echo  Fehler beim Starten. Ist Python installiert?
    pause
)
