@echo off
title Detener Bot Soldent
echo ==============================================
echo    DETENIENDO BOT DE WHATSAPP - SOLDENT
echo ==============================================
echo.
echo Cerrando servidores de Node y Python...
taskkill /F /IM node.exe 2>nul
taskkill /F /IM python.exe 2>nul
echo.
echo ==============================================
echo   El bot se ha DETENIDO con exito.
echo ==============================================
timeout /t 3 /nobreak >nul
