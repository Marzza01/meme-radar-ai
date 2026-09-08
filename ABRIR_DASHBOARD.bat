@echo off
title MEME RADAR AI — Abriendo Dashboard...
color 0B
cd /d "%~dp0"

echo ================================================================
echo    MEME RADAR AI v2.2 — Dashboard Web
echo ================================================================
echo.

:: Verificar si el servidor ya esta corriendo en el puerto 3000
netstat -ano | findstr ":3000" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 (
    echo [OK] Servidor ya esta corriendo en puerto 3000.
    echo      Abriendo navegador...
    goto ABRIR
)

:: Si no esta corriendo, arrancarlo en background
echo [..] Servidor no detectado. Iniciando servidor del dashboard...
echo.

:: Intentar via PM2 primero
npx pm2 describe meme-radar-dashboard >nul 2>&1
if %ERRORLEVEL%==0 (
    npx pm2 start meme-radar-dashboard >nul 2>&1
    echo [OK] Dashboard iniciado via PM2.
) else (
    :: Arrancar directamente con Python en background
    start /B "" python src\dashboard\server.py > logs\dashboard_direct.log 2>&1
    echo [OK] Dashboard iniciado directamente (Python).
)

:: Esperar a que el puerto responda (hasta 10 segundos)
echo [..] Esperando que el servidor responda...
set /a intentos=0
:ESPERAR
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":3000" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 goto LISTO
set /a intentos+=1
if %intentos% LSS 10 goto ESPERAR

echo.
echo [!] El servidor tardo mas de 10 segundos en arrancar.
echo     El dashboard se abrira de todas formas (intentara reconectar solo).
goto ABRIR

:LISTO
echo [OK] Servidor respondiendo en http://localhost:3000
echo.

:ABRIR
echo ================================================================
echo   Abriendo Dashboard en tu navegador...
echo ================================================================
start http://localhost:3000
echo.
echo [OK] Dashboard abierto. Puedes cerrar esta ventana.
echo.
timeout /t 3 /nobreak >nul
exit
