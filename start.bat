@echo off
chcp 65001 >nul
cd /d "%~dp0"
title CallBrief — запуск

if not exist ".venv\Scripts\python.exe" (
  echo Не найдено виртуальное окружение .venv.
  echo Сначала выполните установку из README: python -m venv .venv и pip install -r requirements.txt
  pause
  exit /b 1
)

echo Останавливаю старые копии, чтобы не было двух серверов...
taskkill /f /im ngrok.exe >nul 2>&1
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

echo Запускаю сервер...
start "CallBrief - сервер (не закрывать)" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --host 127.0.0.1 --proxy-headers --forwarded-allow-ips=*"
timeout /t 5 /nobreak >nul

rem Туннель нужен только для панели в карточке Битрикс24: портал должен видеть приложение из интернета
if exist "tools\ngrok.exe" if exist "tools\ngrok.yml" (
  echo Запускаю туннель ngrok для Битрикс24...
  start "CallBrief - туннель (не закрывать)" cmd /k "tools\ngrok.exe http 8000 --config tools\ngrok.yml"
)

start "" "http://127.0.0.1:8000/app"
echo.
echo Готово: приложение открыто в браузере — http://127.0.0.1:8000/app
echo Пока работаете, не закрывайте окно «сервер». Чтобы всё выключить — закройте его.
echo.
timeout /t 10
