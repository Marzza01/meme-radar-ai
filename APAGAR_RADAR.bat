@echo off
title MEME RADAR AI — Apagar
echo ========================================================
echo   DETENIENDO MEME RADAR AI...
echo ========================================================
npx pm2 stop ecosystem.config.js
echo.
echo [OK] Sistema (Radar y Dashboard) apagado completamente.
timeout /t 3
exit
