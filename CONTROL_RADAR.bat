@echo off
title MEME RADAR AI — Panel de Control
color 0B

:MENU
cls
echo ================================================================
echo           🛰️  MEME RADAR AI v2.2 — PANEL DE CONTROL
echo ================================================================
echo.
echo   [1] 🟢 ENCENDER Sistema Completo (Radar + Dashboard en segundo plano)
echo   [2] 🔴 APAGAR Sistema Completo (Detener Radar y Dashboard)
echo   [3] 🔄 REINICIAR Sistema (Aplicar cambios o refrescar)
echo   [4] 📊 ESTADO del Sistema (Ver procesos activos y memoria)
echo   [5] 📜 VER LOGS en Vivo (Monitoreo de alertas en tiempo real)
echo   [6] 📋 GENERAR Informe Diario (Ejecutar reporte ahora)
echo   [7] 🌐 ABRIR Dashboard Web (Interfaz Stakent en Navegador)
echo   [8] ❌ Salir
echo.
echo ================================================================
set /p OPCION="Selecciona una opcion [1-8]: "

if "%OPCION%"=="1" goto ENCENDER
if "%OPCION%"=="2" goto APAGAR
if "%OPCION%"=="3" goto REINICIAR
if "%OPCION%"=="4" goto ESTADO
if "%OPCION%"=="5" goto LOGS
if "%OPCION%"=="6" goto REPORTE
if "%OPCION%"=="7" goto DASHBOARD
if "%OPCION%"=="8" goto SALIR

echo Opcion invalida.
timeout /t 2 >nul
goto MENU

:ENCENDER
cls
echo ================================================================
echo   Iniciando Meme Radar AI + Dashboard 24/7 con PM2...
echo ================================================================
npx pm2 start ecosystem.config.js
npx pm2 save
echo.
echo Sistema encendido con exito!
echo Puedes acceder al Dashboard en: http://localhost:3000
echo.
pause
goto MENU

:APAGAR
cls
echo ================================================================
echo   Deteniendo Meme Radar AI y Dashboard...
echo ================================================================
npx pm2 stop ecosystem.config.js
echo.
echo Sistema apagado correctamente.
echo.
pause
goto MENU

:REINICIAR
cls
echo ================================================================
echo   Reiniciando Meme Radar AI...
echo ================================================================
npx pm2 restart meme-radar-engine
echo.
echo Radar reiniciado con exito.
echo.
pause
goto MENU

:ESTADO
cls
echo ================================================================
echo   Estado actual de los procesos:
echo ================================================================
npx pm2 status
echo.
pause
goto MENU

:LOGS
cls
echo ================================================================
echo   Mostrando logs en vivo (Presiona Ctrl+C para salir de los logs)...
echo ================================================================
npx pm2 logs meme-radar-engine
pause
goto MENU

:REPORTE
cls
echo ================================================================
echo   Generando informe diario de la bitacora...
echo ================================================================
python src/bitacora/reporter.py
echo.
pause
goto MENU

:DASHBOARD
cls
echo ================================================================
echo   Iniciando Dashboard (con arranque automatico del servidor)...
echo ================================================================
call "%~dp0ABRIR_DASHBOARD.bat"
goto MENU

:SALIR
exit
