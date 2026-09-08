@echo off
title MEME RADAR AI — Encender
echo ========================================================
echo   ENCENDIENDO MEME RADAR AI (MODO 24/7 PM2)
echo ========================================================
npx pm2 start ecosystem.config.js
npx pm2 save
echo.
echo [OK] Radar encendido y operando en segundo plano!
timeout /t 3
exit
