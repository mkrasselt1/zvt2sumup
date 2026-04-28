@echo off
chcp 65001 >nul 2>&1
echo Beende ZVT-zu-SumUp Gateway...
taskkill /f /fi "WINDOWTITLE eq ZVT-zu-SumUp Gateway" >nul 2>&1
echo Gateway wurde beendet.
timeout /t 3
