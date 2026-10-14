@echo off
chcp 65001 >nul
title Renovación de Token - Google Calendar Soldent
echo =====================================================================
echo  🦷 SOLDENT - RENOVACIÓN DE GOOGLE CALENDAR
echo =====================================================================
echo.
echo  Abriendo autorización en tu navegador...
echo.
.\venv\Scripts\python.exe scripts\tools\renovar_google_token.py
echo.
pause
