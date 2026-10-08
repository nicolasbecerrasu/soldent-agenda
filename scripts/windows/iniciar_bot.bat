@echo off
title Iniciar Bot Soldent
echo ==============================================
echo    INICIANDO BOT DE WHATSAPP - SOLDENT
echo ==============================================
echo.

:: 1. Iniciar Pasarela de WhatsApp
echo [1/2] Iniciando Pasarela de WhatsApp...
cd /d "%~dp0whatsapp-gateway"
start "1. Pasarela WhatsApp (Gateway)" cmd /k "node server.js"

:: Esperar 3 segundos para que cargue el puerto 8080
timeout /t 3 /nobreak >nul

:: 2. Iniciar Servidor de Inteligencia Artificial (FastAPI + Gemini)
echo [2/2] Iniciando Asistente Virtual IA...
cd /d "%~dp0"
start "2. Asistente IA Soldent (Python)" cmd /k "python whatsapp_bot.py"

echo.
echo ==============================================
echo   Listos! El bot ya esta activo.
echo   Para reiniciar en el futuro, solo cierra 
echo   las ventanas y vuelve a abrir este archivo.
echo ==============================================
pause
