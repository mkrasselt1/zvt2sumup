@echo off
chcp 65001 >nul 2>&1
title ZVT-zu-SumUp Gateway - Dienst entfernen
cd /d "%~dp0"

echo.
echo ========================================================
echo   ZVT-zu-SumUp Gateway - Dienst entfernen
echo ========================================================
echo.

:: Admin-Rechte pruefen
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo FEHLER: Dieses Skript benoetigt Administrator-Rechte!
    echo.
    echo Bitte Rechtsklick auf die Datei ^> "Als Administrator ausfuehren"
    echo.
    pause
    exit /b 1
)

echo [1/2] Stoppe Dienst...
python -m gateway.win_service stop 2>nul
echo   OK (oder war bereits gestoppt)

echo.
echo [2/2] Entferne Dienst...
python -m gateway.win_service remove
if %ERRORLEVEL% neq 0 (
    echo.
    echo WARNUNG: Dienst konnte nicht entfernt werden.
    echo Moeglicherweise war er nicht installiert.
    echo.
) else (
    echo.
    echo Dienst erfolgreich entfernt.
)

echo.
echo Das Gateway kann weiterhin manuell mit start.bat
echo gestartet werden.
echo.
pause
