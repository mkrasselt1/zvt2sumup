@echo off
chcp 65001 >nul 2>&1
title ZVT-zu-SumUp Gateway - Installation
color 0F

echo.
echo ========================================================
echo   ZVT-zu-SumUp Gateway - Automatische Installation
echo ========================================================
echo.
echo Dieses Skript installiert alle notwendigen Komponenten
echo fuer das ZVT-zu-SumUp Gateway.
echo.
echo Was wird installiert:
echo   - Python (falls nicht vorhanden)
echo   - Benoetigte Python-Pakete (pyserial, requests)
echo   - Konfigurationsdatei wird erstellt
echo.
pause

echo.
echo [1/4] Pruefe Python-Installation...
echo ------------------------------------------------

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do (
        echo   Python gefunden: %%i
    )
    goto :python_ok
)

where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%i in ('python3 --version 2^>^&1') do (
        echo   Python3 gefunden: %%i
    )
    goto :python_ok
)

echo   Python wurde NICHT gefunden!
echo.
echo   Python wird jetzt heruntergeladen und installiert...
echo   (Bitte folgen Sie dem Installationsassistenten)
echo.

:: Python via winget installieren (Windows 10/11)
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   Python wurde erfolgreich installiert!
    echo   WICHTIG: Bitte starten Sie dieses Skript erneut,
    echo   damit Python im Pfad gefunden wird.
    echo.
    pause
    exit /b 0
)

:: Fallback: Manuelle Anleitung
echo   Automatische Installation fehlgeschlagen.
echo.
echo   Bitte installieren Sie Python manuell:
echo     1. Gehen Sie zu https://www.python.org/downloads/
echo     2. Laden Sie Python 3.12 oder neuer herunter
echo     3. WICHTIG: Setzen Sie den Haken bei
echo        "Add Python to PATH"
echo     4. Klicken Sie auf "Install Now"
echo     5. Fuehren Sie dieses Skript danach erneut aus
echo.
pause
exit /b 1

:python_ok
echo.
echo [2/4] Installiere benoetigte Pakete...
echo ------------------------------------------------

cd /d "%~dp0"
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo   FEHLER: Paketinstallation fehlgeschlagen!
    echo   Bitte pruefen Sie Ihre Internetverbindung.
    pause
    exit /b 1
)
echo   Pakete erfolgreich installiert.

echo.
echo [3/4] Erstelle Konfiguration...
echo ------------------------------------------------

if exist config.ini (
    echo   config.ini existiert bereits - wird nicht ueberschrieben.
) else (
    python -c "from gateway.config import GatewayConfig; GatewayConfig()"
    echo   Standard-Konfiguration erstellt: config.ini
)

echo.
echo [4/4] Erstelle Verknuepfungen...
echo ------------------------------------------------

:: Desktop-Verknuepfung fuer Start
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine($ws.SpecialFolders('Desktop'), 'ZVT-SumUp Gateway.lnk')); $s.TargetPath = '%~dp0start.bat'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = 'shell32.dll,21'; $s.Description = 'ZVT-zu-SumUp Gateway starten'; $s.Save()" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   Desktop-Verknuepfung erstellt.
) else (
    echo   Desktop-Verknuepfung konnte nicht erstellt werden (nicht kritisch).
)

echo.
echo ========================================================
echo   Installation abgeschlossen!
echo ========================================================
echo.
echo   Naechster Schritt:
echo     Fuehren Sie 'setup.bat' aus, um Ihre
echo     SumUp-Zugangsdaten einzugeben.
echo.
echo   Oder bearbeiten Sie die config.ini direkt.
echo.
echo   Danach starten Sie das Gateway mit 'start.bat'.
echo.
pause
