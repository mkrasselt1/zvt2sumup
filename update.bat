@echo off
chcp 65001 >nul 2>&1
title ZVT-zu-SumUp Gateway - Updater
cd /d "%~dp0"

:: Pruefe ob Gateway als Dienst laeuft
sc query ZVT2SumUpGateway 2>nul | findstr "RUNNING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo.
    echo HINWEIS: Das Gateway laeuft als Windows-Dienst.
    echo Nach dem Update wird der Dienst automatisch neu gestartet.
    echo.
    set RESTART_SERVICE=1
) else (
    set RESTART_SERVICE=0
)

python -m gateway.updater

:: Dienst neu starten wenn er vorher lief
if "%RESTART_SERVICE%"=="1" (
    echo.
    echo Starte Dienst neu...
    net stop ZVT2SumUpGateway >nul 2>&1
    net start ZVT2SumUpGateway >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo Dienst erfolgreich neu gestartet.
    ) else (
        echo WARNUNG: Dienst konnte nicht neu gestartet werden.
        echo Bitte manuell ueber services.msc starten.
    )
    echo.
    pause
)
