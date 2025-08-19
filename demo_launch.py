#!/usr/bin/env python3
"""
Демонстрационный скрипт для быстрого запуска и проверки API сервера Mini App

Запускает API сервер в режиме демонстрации с дополнительными логами.
"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    """Главная функция для запуска демо"""
    
    print("🚀 AI Scientific Assistant 2.0 - Demo Launcher")
    print("=" * 55)
    
    # Проверяем наличие необходимых файлов
    root_dir = Path(__file__).parent
    required_files = [
        "api/main.py",
        "webapp/templates/library.html", 
        "webapp/static/app.js",
        "webapp/static/styles.css"
    ]
    
    missing_files = [f for f in required_files if not (root_dir / f).exists()]
    if missing_files:
        print("❌ Отсутствуют необходимые файлы:")
        for f in missing_files:
            print(f"  - {f}")
        return 1
    
    print("✅ Все необходимые файлы найдены")
    
    # Проверяем переменные окружения
    if not os.getenv("WEBAPP_URL"):
        print("⚠️  WEBAPP_URL не установлен, используем localhost")
        os.environ["WEBAPP_URL"] = "http://localhost:8000"
    
    if not os.getenv("BOT_TOKEN"):
        print("⚠️  BOT_TOKEN не установлен - Mini App будет работать в demo режиме")
        os.environ["BOT_TOKEN"] = "demo_token"
        
    if not os.getenv("LLM_API_KEY"):
        print("⚠️  LLM_API_KEY не установлен - используем demo ключ")
        os.environ["LLM_API_KEY"] = "demo_key"
    
    print("\n🌐 Запуск API сервера...")
    print("📱 Mini App будет доступен по адресу: http://localhost:8000")
    print("🔧 API документация: http://localhost:8000/docs")
    
    # Выводим доступные эндпоинты
    print("\n📋 Доступные API эндпоинты:")
    endpoints = [
        ("GET /", "Главная страница Mini App"),
        ("GET /api/v1/user/info", "Информация о пользователе"),
        ("GET /api/v1/library", "Библиотека пользователя"),
        ("POST /api/v1/search", "Поиск научных статей"),
        ("POST /api/v1/recommendations", "Персональные рекомендации"),
        ("POST /api/v1/chat", "AI-чат ассистент"),
        ("DELETE /api/v1/library/{id}", "Удаление статьи"),
        ("POST /api/v1/library/{id}/tags", "Редактирование тегов"),
    ]
    
    for endpoint, description in endpoints:
        print(f"  {endpoint:<35} - {description}")
    
    print("\n" + "=" * 55)
    print("💡 Для полного функционала:")
    print("   1. Настройте переменные окружения в .env")
    print("   2. Запустите Telegram бота: python main.py")  
    print("   3. Используйте команду /library в боте")
    print("\n🔧 Для остановки сервера: Ctrl+C")
    print("=" * 55)
    
    try:
        # Меняем рабочую директорию
        os.chdir(root_dir)
        
        # Определяем Python executable
        python_exe = sys.executable
        
        # Запускаем API сервер
        subprocess.run([
            python_exe, "run_api.py"
        ], check=True)
        
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен пользователем")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Ошибка запуска API сервера: {e}")
        return 1
    except Exception as e:
        print(f"\n💥 Неожиданная ошибка: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
