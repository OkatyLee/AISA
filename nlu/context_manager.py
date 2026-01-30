"""
Context Manager - управление контекстом диалога.

Хранит историю диалога в SQLite, кэширует в памяти.
Автоматически очищает неиспользуемый кэш.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import aiosqlite

from nlu.models import UserContext, ConversationTurn, Intent, Entity, EntityType
from utils.logger import setup_logger

logger = setup_logger(name="context_manager", level=logging.INFO)


class ContextManager:
    """
    Менеджер контекста диалога.
    
    Хранит историю разговоров в SQLite, кэширует активные сессии в памяти.
    Автоматически очищает неактивные контексты из кэша.
    """
    
    def __init__(
        self,
        db_path: str = "db/scientific_assistant.db",
        cache_ttl_minutes: int = 30,  # TTL кэша в минутах
        cleanup_interval_minutes: int = 5,  # Интервал очистки кэша
        max_cache_size: int = 1000,  # Максимальный размер кэша
    ):
        self.db_path = db_path
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.cleanup_interval = timedelta(minutes=cleanup_interval_minutes)
        self.max_cache_size = max_cache_size
        
        self._cache: Dict[int, UserContext] = {}
        self._last_access: Dict[int, datetime] = {}  # Время последнего доступа
        self._initialized = False
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def init_db(self):
        """Инициализация таблиц в БД."""
        if self._initialized:
            return
            
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_contexts (
                    user_id INTEGER PRIMARY KEY,
                    conversation_history TEXT,
                    current_topic TEXT,
                    current_articles TEXT,
                    user_preferences TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            
        self._initialized = True
        
        # Запускаем фоновую задачу очистки кэша
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("ContextManager инициализирован")
    
    async def close(self):
        """Закрытие менеджера контекста."""
        # Останавливаем задачу очистки
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Сохраняем все контексты из кэша в БД
        await self._flush_cache()
        logger.info("ContextManager закрыт")
    
    async def _cleanup_loop(self):
        """Фоновая задача для периодической очистки кэша."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval.total_seconds())
                await self._cleanup_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в cleanup loop: {e}")
    
    async def _cleanup_cache(self):
        """Очистка устаревших контекстов из кэша."""
        now = datetime.now()
        expired_users = []
        
        for user_id, last_access in self._last_access.items():
            if now - last_access > self.cache_ttl:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            # Сохраняем контекст в БД перед удалением из кэша
            if user_id in self._cache:
                await self._save_context(self._cache[user_id])
                del self._cache[user_id]
            if user_id in self._last_access:
                del self._last_access[user_id]
        
        if expired_users:
            logger.debug(f"Очищено {len(expired_users)} устаревших контекстов из кэша")
        
        # Если кэш всё ещё слишком большой, удаляем самые старые
        if len(self._cache) > self.max_cache_size:
            sorted_users = sorted(
                self._last_access.items(),
                key=lambda x: x[1]
            )
            to_remove = len(self._cache) - self.max_cache_size
            for user_id, _ in sorted_users[:to_remove]:
                if user_id in self._cache:
                    await self._save_context(self._cache[user_id])
                    del self._cache[user_id]
                if user_id in self._last_access:
                    del self._last_access[user_id]
            logger.debug(f"Удалено {to_remove} контекстов из-за превышения лимита кэша")
    
    async def _flush_cache(self):
        """Сохранить все контексты из кэша в БД."""
        for user_id, context in self._cache.items():
            try:
                await self._save_context(context)
            except Exception as e:
                logger.error(f"Ошибка при сохранении контекста {user_id}: {e}")
        logger.info(f"Сохранено {len(self._cache)} контекстов в БД")
    
    async def get_context(self, user_id: int) -> UserContext:
        """
        Получить контекст пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            UserContext
        """
        await self.init_db()
        
        # Обновляем время последнего доступа
        self._last_access[user_id] = datetime.now()
        
        # Проверяем кэш
        if user_id in self._cache:
            return self._cache[user_id]
        
        # Загружаем из БД
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM user_contexts WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
        
        if row:
            context = self._deserialize(dict(row))
        else:
            context = UserContext(user_id=user_id)
            
        self._cache[user_id] = context
        return context
    
    async def update_context(
        self,
        user_id: int,
        message: str,
        intent: Intent,
        entities: List[Entity],
        bot_response: Optional[str] = None,
        search_results: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Обновить контекст после обработки сообщения.
        
        Args:
            user_id: ID пользователя
            message: Сообщение пользователя
            intent: Определённое намерение
            entities: Извлечённые сущности
            bot_response: Ответ бота
            search_results: Результаты поиска (если есть)
        """
        context = await self.get_context(user_id)
        
        # Создаём новый ход диалога
        turn = ConversationTurn(
            timestamp=datetime.now(),
            user_message=message,
            intent=intent,
            entities=entities,
            bot_response=bot_response,
            search_results=search_results,
        )
        context.add_turn(turn)
        
        # Обновляем текущую тему
        topic_entities = [e for e in entities if e.type == EntityType.TOPIC]
        if topic_entities:
            context.current_topic = topic_entities[0].normalized_value or topic_entities[0].value
        
        # Обновляем текущие статьи
        if search_results:
            context.current_articles = search_results
            
        # Сохраняем
        await self._save_context(context)
        self._cache[user_id] = context
    
    async def set_current_articles(
        self,
        user_id: int,
        articles: List[Dict[str, Any]],
    ):
        """
        Установить текущие статьи в контексте.
        
        Args:
            user_id: ID пользователя
            articles: Список статей
        """
        context = await self.get_context(user_id)
        context.current_articles = articles
        context.updated_at = datetime.now()
        
        await self._save_context(context)
        self._cache[user_id] = context
    
    async def clear_context(self, user_id: int):
        """Очистить контекст пользователя."""
        context = await self.get_context(user_id)
        context.clear()
        
        await self._save_context(context)
        self._cache[user_id] = context
    
    async def _save_context(self, context: UserContext):
        """Сохранить контекст в БД."""
        await self.init_db()
        
        data = self._serialize(context)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO user_contexts
                (user_id, conversation_history, current_topic, current_articles,
                 user_preferences, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, data)
            await db.commit()
    
    def _serialize(self, context: UserContext) -> tuple:
        """Сериализация контекста для БД."""
        history = []
        for turn in context.conversation_history:
            history.append({
                "timestamp": turn.timestamp.isoformat(),
                "user_message": turn.user_message,
                "intent": turn.intent.value,
                "entities": [
                    {
                        "type": e.type.value,
                        "value": e.value,
                        "confidence": e.confidence,
                        "normalized_value": e.normalized_value,
                    }
                    for e in turn.entities
                ],
                "bot_response": turn.bot_response,
                "search_results": turn.search_results,
            })
        
        return (
            context.user_id,
            json.dumps(history, ensure_ascii=False),
            context.current_topic,
            json.dumps(context.current_articles, ensure_ascii=False),
            json.dumps(context.user_preferences, ensure_ascii=False),
            context.created_at.isoformat(),
            context.updated_at.isoformat(),
        )
    
    def _deserialize(self, row: dict) -> UserContext:
        """Десериализация контекста из БД."""
        history = []
        for turn_data in json.loads(row.get("conversation_history") or "[]"):
            entities = []
            for e_data in turn_data.get("entities", []):
                try:
                    entities.append(Entity(
                        type=EntityType(e_data["type"]),
                        value=e_data["value"],
                        confidence=e_data.get("confidence", 1.0),
                        normalized_value=e_data.get("normalized_value"),
                    ))
                except (ValueError, KeyError):
                    continue
            
            try:
                history.append(ConversationTurn(
                    timestamp=datetime.fromisoformat(turn_data["timestamp"]),
                    user_message=turn_data["user_message"],
                    intent=Intent(turn_data["intent"]),
                    entities=entities,
                    bot_response=turn_data.get("bot_response"),
                    search_results=turn_data.get("search_results"),
                ))
            except (ValueError, KeyError):
                continue
        
        return UserContext(
            user_id=row["user_id"],
            conversation_history=history,
            current_topic=row.get("current_topic"),
            current_articles=json.loads(row.get("current_articles") or "[]"),
            user_preferences=json.loads(row.get("user_preferences") or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else datetime.now(),
        )
