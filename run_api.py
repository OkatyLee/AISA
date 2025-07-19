"""
Скрипт запуска API сервера для Telegram Mini App
"""

import uvicorn
import os
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent
sys.path.append(str(root_dir))

def main():
    """Запуск API сервера"""
    
    # Проверяем наличие необходимых файлов
    required_files = [
        root_dir / "webapp" / "templates" / "library.html",
        root_dir / "webapp" / "static" / "app.js",
        root_dir / "webapp" / "static" / "styles.css"
    ]
    
    missing_files = [f for f in required_files if not f.exists()]
    if missing_files:
        print("❌ Отсутствуют необходимые файлы:")
        for f in missing_files:
            print(f"  - {f}")
        return
    
    print("🚀 Запуск API сервера для Telegram Mini App...")
    print("📱 Mini App будет доступен по адресу: http://localhost:8000")
    print("🔧 API эндпоинты:")
    print("  - GET  /api/v1/library - получение библиотеки")
    print("  - DELETE /api/v1/library/{id} - удаление статьи")
    print("  - GET  /api/v1/stats - статистика")
    print("  - GET  /api/v1/user/info - информация о пользователе")
    print("=" * 60)
    
    try:
        # Меняем рабочую директорию на корневую
        os.chdir(root_dir)
        
        # Запуск сервера
        uvicorn.run(
            "api.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            reload_dirs=[str(root_dir)],
            log_level="info",
            http='auto'
        )
    except KeyboardInterrupt:
        print("\n👋 Сервер остановлен")
    except Exception as e:
        print(f"❌ Ошибка запуска сервера: {e}")

if __name__ == "__main__":
    main()
