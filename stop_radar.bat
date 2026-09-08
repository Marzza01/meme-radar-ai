@echo off
title MEME RADAR AI - Detener PM2
echo Deteniendo Meme Radar AI...
npx pm2 stop meme-radar-engine
npx pm2 status
pause
