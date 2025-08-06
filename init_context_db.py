#!/usr/bin/env python3
"""
Скрипт для инициализации базы данных контекста пользователей.
"""
import asyncio
import os
import sys

# Добавляем корневую папку проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nlp.context_manager import ContextManager

async def init_database():
    """Инициализирует базу данных для хранения контекста пользователей."""
    
    # Путь к базе данных
    db_path = "db/scientific_assistant.db"
    
    # Создаем директорию db если она не существует
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    print("=" * 50)
    print("ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ КОНТЕКСТА")
    print("=" * 50)
    print(f"Путь к БД: {db_path}")
    
    try:
        # Создаем экземпляр ContextManager
        context_manager = ContextManager(db_path)
        
        # Инициализируем базу данных
        await context_manager.init_db()
        
        print("✅ База данных успешно инициализирована!")
        print("✅ Таблица user_context создана")
        
        # Проверяем, что таблица создалась
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_context'") as cursor:
                table = await cursor.fetchone()
                if table:
                    print("✅ Таблица user_context найдена в базе данных")
                    
                    # Показываем структуру таблицы
                    async with db.execute("PRAGMA table_info(user_context)") as cursor:
                        columns = await cursor.fetchall()
                        print("\n📋 Структура таблицы user_context:")
                        for col in columns:
                            print(f"   - {col[1]} ({col[2]})")
                else:
                    print("❌ Таблица user_context не найдена")
                    
    except Exception as e:
        print(f"❌ Ошибка при инициализации: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("ИНИЦИАЛИЗАЦИЯ ЗАВЕРШЕНА")
    print("=" * 50)
    return True

async def test_context_operations():
    """Тестирует основные операции с контекстом."""
    
    print("\n--- ТЕСТИРОВАНИЕ ОПЕРАЦИЙ С КОНТЕКСТОМ ---")
    
    db_path = "db/scientific_assistant.db"
    context_manager = ContextManager(db_path)
    
    try:
        from utils.nlu.intents import Intent
        from utils.nlu.entities import Entity, EntityType
        
        test_user_id = 99999
        
        # Тест 1: Получение нового контекста
        print("1. Получение контекста для нового пользователя...")
        context = await context_manager.get_user_context(test_user_id)
        print(f"   ✅ Создан контекст для пользователя {test_user_id}")
        
        # Тест 2: Обновление контекста
        print("2. Обновление контекста...")
        test_entities = [
            Entity(
                type=EntityType.TOPIC,
                value="машинное обучение",
                confidence=0.9,
                start_pos=0,
                end_pos=10
            )
        ]
        
        await context_manager.update_user_context(
            user_id=test_user_id,
            message="Найди статьи про машинное обучение",
            intent=Intent.SEARCH,
            entities=test_entities,
            bot_response="Ищу статьи по машинному обучению...",
            search_results=["result1", "result2"]
        )
        print("   ✅ Контекст обновлен")
        
        # Тест 3: Проверка сохранения
        print("3. Проверка сохранения в базе данных...")
        saved_context = await context_manager.get_user_context(test_user_id)
        print(f"   ✅ Текущая тема: {saved_context.current_topic}")
        print(f"   ✅ История: {len(saved_context.conversation_history)} записей")
        print(f"   ✅ Результаты поиска: {len(saved_context.last_search_results)} элементов")
        
        # Очистка тестовых данных
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            await db.execute("DELETE FROM user_context WHERE user_id = ?", (test_user_id,))
            await db.commit()
        print("   ✅ Тестовые данные очищены")
        
    except Exception as e:
        print(f"   ❌ Ошибка в тестах: {e}")
        return False
    
    print("✅ Все тесты пройдены успешно!")
    return True

if __name__ == "__main__":
    async def main():
        success = await init_database()
        if success:
            await test_context_operations()
    
    asyncio.run(main())
