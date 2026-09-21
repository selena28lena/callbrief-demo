@echo off
chcp 65001 >nul
cd /d "%~dp0"
title CallBrief — запуск

echo Останавливаю старые копии, чтобы не было двух серверов...
taskkill /f /im ngrok.exe >nul 2>&1
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

echo Запускаю сервер...
start "CallBrief - сервер (не закрывать)" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --host 127.0.0.1 --proxy-headers --forwarded-allow-ips=*"
timeout /t 5 /nobreak >nul

echo Запускаю туннель ngrok...
start "CallBrief - туннель (не закрывать)" cmd /k "tools\ngrok.exe http 8000 --config tools\ngrok.yml"

echo.
echo Готово. Приложение:  https://revolt-slighting-ambulance.ngrok-free.dev/app
echo Панель в Битриксе заработает сама — адрес не меняется.
echo.
echo Пока работаете, НЕ закрывайте два чёрных окна: «сервер» и «туннель».
echo Чтобы всё выключить — просто закройте их.
echo.
timeout /t 15
