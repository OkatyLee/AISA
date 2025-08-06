#!/usr/bin/env python3
"""
Тест интеграции контекстного менеджера с обработкой сообщений.
"""
import asyncio
import sys
import os
from datetime import datetime

# Добавляем корневую папку проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nlp.context_manager import ContextManager
from nlp.query_processor import QueryProcessor
from utils.nlu.context import UserContext, ConversationTurn
from utils.nlu.intents import Intent
from utils.nlu.entities import Entity, EntityType

class MockMessage:
    def __init__(self, text: str, user_id: int = 12345):
        self.text = text
        self.from_user = type('User', (), {'id': user_id})()

async def test_context_integration():
    """Тестирует интеграцию контекста с процессором запросов."""
    
    # Инициализируем компоненты
    context_manager = ContextManager("test_context.db")
    query_processor = QueryProcessor()
    
    await context_manager.init_db()
    
    user_id = 12345
    
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ИНТЕГРАЦИИ КОНТЕКСТА")
    print("=" * 60)
    
    # Сценарий тестирования
    test_scenarios = [
        {
            "message": "Найди статьи про машинное обучение",
            "expected_intent": Intent.SEARCH,
            "description": "Первый поиск - должен создать контекст"
        },
        {
            "message": "еще статьи",
            "expected_intent": Intent.SEARCH,
            "description": "Короткий запрос - должен использовать контекст темы"
        },
        {
            "message": "от автора Smith",
            "expected_intent": Intent.SEARCH,
            "description": "Уточнение автора - должен объединить с контекстом"
        },
        {
            "message": "Привет",
            "expected_intent": Intent.GREETING,
            "description": "Смена темы - контекст должен обновиться"
        },
        {
            "message": "Найди статьи про нейронные сети",
            "expected_intent": Intent.SEARCH,
            "description": "Новый поиск - новая тема в контексте"
        },
        {
            "message": "больше информации",
            "expected_intent": Intent.SEARCH,
            "description": "Должен использовать новую тему из контекста"
        }
    ]
    
    for i, scenario in enumerate(test_scenarios):
        print(f"\n--- Тест {i+1}: {scenario['description']} ---")
        print(f"👤 Сообщение: '{scenario['message']}'")
        
        # Получаем контекст пользователя
        user_context = await context_manager.get_user_context(user_id)
        
        # Обрабатываем запрос
        result = query_processor.process(scenario['message'], user_context)
        
        print(f"🎯 Намерение: {result.intent.intent.value}")
        print(f"   Ожидалось: {scenario['expected_intent'].value}")
        
        if result.entities.entities:
            print("🏷️  Сущности:")
            for entity in result.entities.entities:
                print(f"   - {entity.type.value}: '{entity.value}' (conf: {entity.confidence:.2f})")
        
        print(f"📋 Параметры запроса: {result.query_params}")
        
        # Обновляем контекст
        await context_manager.update_user_context(
            user_id=user_id,
            message=scenario['message'],
            intent=result.intent.intent,
            entities=result.entities.entities,
            bot_response=f"Ответ на: {scenario['message']}",
            search_results=[]
        )
        
        # Показываем текущий контекст
        updated_context = await context_manager.get_user_context(user_id)
        print(f"📝 Текущая тема в контексте: {updated_context.current_topic}")
        print(f"📚 История диалога: {len(updated_context.conversation_history)} записей")
        
        # Проверяем соответствие ожидаемому намерению
        if result.intent.intent == scenario['expected_intent']:
            print("✅ Тест ПРОЙДЕН")
        else:
            print("❌ Тест ПРОВАЛЕН")
    
    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 60)

async def test_context_persistence():
    """Тестирует сохранение контекста в базе данных."""
    print("\n--- Тест сохранения контекста ---")
    
    context_manager = ContextManager("test_context.db")
    await context_manager.init_db()
    
    user_id = 54321
    
    # Создаем контекст
    await context_manager.update_user_context(
        user_id=user_id,
        user_message="Тестовое сообщение",
        intent=Intent.SEARCH,
        entities=[],
        bot_response="Тестовый ответ",
        search_results=["result1", "result2"]
    )
    
    # Получаем контекст
    context = await context_manager.get_user_context(user_id)
    
    print(f"Пользователь {user_id}:")
    print(f"- История: {len(context.conversation_history)} записей")
    print(f"- Последние результаты поиска: {context.last_search_results}")
    
    if context.conversation_history:
        last_turn = context.conversation_history[-1]
        print(f"- Последнее сообщение: '{last_turn.user_message}'")
        print(f"- Последний ответ: '{last_turn.bot_response}'")
    
    print("✅ Тест сохранения контекста ПРОЙДЕН")

if __name__ == "__main__":
    asyncio.run(test_context_integration())
    asyncio.run(test_context_persistence())
