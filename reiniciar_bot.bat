@echo off
title Reiniciar Bot Soldent
echo ==============================================
echo    REINICIANDO BOT DE WHATSAPP - SOLDENT
echo ==============================================
echo.

echo [1/3] Cerrando instancias anteriores...
taskkill /F /FI "WINDOWTITLE eq 1. Pasarela WhatsApp*" /T 2>nul
taskkill /F /FI "WINDOWTITLE eq 2. Asistente IA*" /T 2>nul
timeout /t 2 /nobreak >nul

echo [2/3] Iniciando Pasarela de WhatsApp...
cd /d "%~dp0whatsapp-gateway"
start "1. Pasarela WhatsApp (Gateway)" cmd /k "node server.js"

timeout /t 3 /nobreak >nul

echo [3/3] Iniciando Asistente IA Soldent...
cd /d "%~dp0"
start "2. Asistente IA Soldent (Python)" cmd /k "python whatsapp_bot.py"

echo.
echo ==============================================
echo   Listos! El bot fue reiniciado con exito.
echo ==============================================
pause
