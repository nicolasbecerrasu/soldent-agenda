@echo off
title Respaldo de Pacientes - Soldent
echo ========================================================
echo   GENERANDO BACKUP DE PACIENTES EN EXCEL (SOLDENT)
echo ========================================================
python exportar_pacientes_excel.py
echo.
echo ========================================================
echo   RESPALDO COMPLETADO EN: backup_pacientes_soldent.xlsx
echo ========================================================
pause
