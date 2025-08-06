from datetime import timedelta, datetime
from utils.nlu.context import ConversationTurn, UserContext
from typing import Any, Dict, List, Optional
import aiosqlite
import json
from utils.nlu.entities import Entity, EntityType
from utils.nlu.intents import Intent

class ContextManager:
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.context_cache: Dict[int, UserContext] = {}
        self.cache_ttl = timedelta(hours=1) 
        
    async def init_db(self):
        """
        Инициализация базы данных для хранения контекста пользователя.
        Здесь можно подключиться к базе данных или создать таблицы.
        """
        # Пример инициализации базы данных
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_context (
                    user_id INTEGER PRIMARY KEY,
                    conversation_history TEXT,
                    current_topic TEXT,
                    user_preferences TEXT,
                    last_search_results TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    async def get_user_context(self, user_id: int) -> UserContext:
        #
        if user_id in self.context_cache:
            context = self.context_cache[user_id]
            if datetime.now() - context.updated_at < self.cache_ttl:
                return context
        
        #
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                    "SELECT * FROM user_context WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
        
        if row:
            context = self._deserialize_context(row)
        else:
            context = UserContext(user_id=user_id)
        
        self.context_cache[user_id] = context
        return context

    async def update_user_context(
        self,
        user_id: int,
        message: str,
        intent: Intent,
        entities: List[Entity],
        bot_response: Optional[str] = None,
        search_results: Optional[List[str]] = None
    ):
        context = await self.get_user_context(user_id)
        
        turn = ConversationTurn(
            timestamp=datetime.now(),
            user_message=message,
            intent=intent,
            entities=entities,
            bot_response=bot_response,
            search_results=search_results
        )
        
        context.add_turn(turn)

        topic_entities = [e for e in entities if e.type == EntityType.TOPIC]
        if topic_entities:
            context.current_topic = topic_entities[0].normalized_value
            
        if search_results:
            context.last_search_results = search_results
            
        await self._save_context(context)    
            
        self.context_cache[user_id] = context
        
    async def _save_context(self, context: UserContext):
        
        serialized_data = self._serialize_context(context)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO user_context
                (user_id, conversation_history, current_topic, user_preferences,
                last_search_results, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, serialized_data)
            await db.commit()
            
    def _serialize_context(self, context: UserContext) -> tuple:
        return (
            context.user_id,
            json.dumps([self._turn_to_dict(turn) for turn in context.conversation_history]),
            context.current_topic,
            json.dumps(context.last_search_results),
            json.dumps(context.user_preferences),
            context.created_at.isoformat(),
            context.updated_at.isoformat()
        )
        
    def _turn_to_dict(self, turn: ConversationTurn) -> Dict[str, Any]:
        return {
            "timestamp": turn.timestamp.isoformat(),
            "user_message": turn.user_message,
            "intent": turn.intent.value,
            "entities": [
                {
                    'type': e.type.value,
                    'value': e.value,
                    'confidence': e.confidence,
                    'start_pos': e.start_pos,
                    'end_pos': e.end_pos,
                    'normalized_value': e.normalized_value
                }
                for e in turn.entities
            ],
            "bot_response": turn.bot_response,
            "search_results": turn.search_results
        }
        
    def _deserialize_context(self, row: tuple) -> UserContext:
        user_id, history_json, current_topic, results_json, prefs_json, created_at, updated_at = row
        conversation_history = [
            self._dict_to_turn(turn_dict) for turn_dict in json.loads(history_json)
        ]
        
        return UserContext(
            user_id=user_id,
            conversation_history=conversation_history,
            current_topic=current_topic,
            user_preferences=json.loads(prefs_json),
            last_search_results=json.loads(results_json),
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at)
        )
        
    def _dict_to_turn(self, turn_dict: Dict[str, Any]) -> ConversationTurn:
        entities = [
            Entity(
                type=EntityType(e['type']),
                value=e['value'],
                confidence=e['confidence'],
                start_pos=e['start_pos'],
                end_pos=e['end_pos'],
                normalized_value=e.get('normalized_value', e['value'])
            ) for e in turn_dict.get('entities', [])
        ]
        return ConversationTurn(
            timestamp=datetime.fromisoformat(turn_dict['timestamp']),
            user_message=turn_dict['user_message'],
            intent=Intent(turn_dict['intent']),
            entities=entities,
            bot_response=turn_dict.get('bot_response'),
            search_results=turn_dict.get('search_results')
        )