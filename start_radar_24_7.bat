@echo off
title MEME RADAR AI - 24/7 PM2 Manager
echo ========================================================
echo   MEME RADAR AI v2.2 - MODO 24/7 (PM2 PRODUCTION)
echo ========================================================
echo Iniciando el motor de convergencia, tracker y bot...
npx pm2 start ecosystem.config.js
npx pm2 save
echo.
echo Estado actual:
npx pm2 status
echo.
echo Comandos utiles:
echo   Ver logs en vivo:  npx pm2 logs meme-radar-engine
echo   Detener sistema:   npx pm2 stop meme-radar-engine
echo   Reiniciar:         npx pm2 restart meme-radar-engine
echo ========================================================
pause
