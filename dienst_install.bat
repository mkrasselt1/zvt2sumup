@echo off
chcp 65001 >nul 2>&1
title ZVT-zu-SumUp Gateway - Dienst installieren
cd /d "%~dp0"

echo.
echo ========================================================
echo   ZVT-zu-SumUp Gateway - Als Windows-Dienst einrichten
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

:: Pruefe ob config.ini existiert und gueltig ist
if not exist config.ini (
    echo FEHLER: config.ini nicht gefunden!
    echo Bitte zuerst install.bat und setup.bat ausfuehren.
    echo.
    pause
    exit /b 1
)

python -c "from gateway.config import GatewayConfig; c=GatewayConfig(); exit(0 if c.api_key else 1)" 2>nul
if %ERRORLEVEL% neq 0 (
    echo FEHLER: SumUp API-Schluessel nicht konfiguriert!
    echo Bitte zuerst setup.bat ausfuehren.
    echo.
    pause
    exit /b 1
)

echo [1/3] Stelle sicher dass pywin32 installiert ist...
python -m pip install pywin32 >nul 2>&1
python -m pywin32_postinstall -install >nul 2>&1
echo   OK

echo.
echo [2/3] Installiere Windows-Dienst...
python -m gateway.win_service install
if %ERRORLEVEL% neq 0 (
    echo.
    echo FEHLER bei der Dienst-Installation!
    echo.
    echo Moegliche Ursachen:
    echo   - Keine Administrator-Rechte
    echo   - Dienst existiert bereits (erst dienst_entfernen.bat ausfuehren)
    echo.
    pause
    exit /b 1
)

echo.
echo [3/3] Starte Dienst...
python -m gateway.win_service start
if %ERRORLEVEL% neq 0 (
    echo.
    echo WARNUNG: Dienst konnte nicht gestartet werden.
    echo Pruefen Sie die Logdatei: zvt2sumup.log
    echo.
    echo Sie koennen den Dienst auch manuell starten:
    echo   - Windows-Taste + R ^> services.msc
    echo   - "ZVT-zu-SumUp Gateway" suchen und starten
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   Dienst erfolgreich installiert und gestartet!
echo ========================================================
echo.
echo   Dienst-Name: ZVT-zu-SumUp Gateway
echo   Starttyp:    Automatisch (startet mit Windows)
echo.
echo   Verwaltung:
echo     - Windows-Dienste: services.msc
echo     - Stoppen:  dienst_entfernen.bat
echo     - Status:   python -m gateway.win_service status
echo     - Logs:     zvt2sumup.log
echo.
pause
