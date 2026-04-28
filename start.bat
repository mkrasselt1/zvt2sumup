@echo off
chcp 65001 >nul 2>&1
title ZVT-zu-SumUp Gateway
cd /d "%~dp0"

:: Pruefe ob config.ini existiert
if not exist config.ini (
    echo.
    echo  config.ini nicht gefunden!
    echo  Bitte zuerst install.bat und dann setup.bat ausfuehren.
    echo.
    pause
    exit /b 1
)

:: Pruefe ob API-Key gesetzt ist
findstr /C:"api_key =" config.ini | findstr /V /C:"api_key = $" | findstr /V /C:"api_key =$" >nul 2>&1
python -c "from gateway.config import GatewayConfig; c=GatewayConfig(); exit(0 if c.api_key else 1)" 2>nul
if %ERRORLEVEL% neq 0 (
    echo.
    echo  SumUp API-Schluessel nicht konfiguriert!
    echo  Bitte zuerst setup.bat ausfuehren.
    echo.
    pause
    exit /b 1
)

echo Starte ZVT-zu-SumUp Gateway...
echo (Zum Beenden: Strg+C oder Fenster schliessen)
echo.

python -m gateway.main

if %ERRORLEVEL% neq 0 (
    echo.
    echo Gateway wurde mit Fehler beendet (Code: %ERRORLEVEL%).
    echo Pruefen Sie die Logdatei: zvt2sumup.log
    echo.
    pause
)
