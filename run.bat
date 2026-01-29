@echo off
echo Starting AISA Environment...

:: 1. API - Запускаем через Python внутри venv
start "API" cmd /k ".venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000"

:: 2. BOT - Тоже через Python внутри venv
start "BOT" cmd /k ".venv\Scripts\python.exe -u main.py"

:: 3. TUNNEL - Указываем полный путь к clo.exe (если он не в Path) или используем имя
:: Если clo.exe лежит в папке проекта или рядом, укажите полный путь
start "TUNNEL" cmd /k "clo publish http 8000"
