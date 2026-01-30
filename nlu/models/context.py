"""Context models for conversation tracking."""

from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from .intents import Intent
from .entities import Entity, EntityType


@dataclass
class ConversationTurn:
    """
    Один ход диалога (сообщение пользователя + ответ бота).
    """
    timestamp: datetime
    user_message: str
    intent: Intent
    entities: List[Entity] = field(default_factory=list)
    bot_response: Optional[str] = None
    search_results: Optional[List[Dict[str, Any]]] = None
    
    def has_entity(self, entity_type: EntityType) -> bool:
        """Проверить наличие сущности определённого типа."""
        return any(e.type == entity_type for e in self.entities)


@dataclass
class UserContext:
    """
    Контекст пользователя для ведения диалога.
    
    Хранит историю разговора, текущую тему, последние результаты поиска.
    """
    user_id: int
    conversation_history: List[ConversationTurn] = field(default_factory=list)
    current_topic: Optional[str] = None
    current_articles: List[Dict[str, Any]] = field(default_factory=list)  # Статьи из последнего поиска
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Настройки контекста
    max_history_size: int = 10
    context_window_hours: int = 24
    
    def add_turn(self, turn: ConversationTurn):
        """Добавить новый ход в историю."""
        self.conversation_history.append(turn)
        self.updated_at = datetime.now()
        
        # Ограничиваем размер истории
        if len(self.conversation_history) > self.max_history_size:
            self.conversation_history = self.conversation_history[-self.max_history_size:]
    
    def get_recent_turns(self, count: int = 5) -> List[ConversationTurn]:
        """Получить последние N ходов."""
        return self.conversation_history[-count:]
    
    def get_recent_entities(self, entity_type: EntityType, hours: int = None) -> List[Entity]:
        """Получить сущности определённого типа из недавней истории."""
        hours = hours or self.context_window_hours
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        entities = []
        for turn in self.conversation_history:
            if turn.timestamp >= cutoff_time:
                entities.extend([e for e in turn.entities if e.type == entity_type])
        return entities
    
    def get_last_search_results(self) -> Optional[List[Dict[str, Any]]]:
        """Получить результаты последнего поиска."""
        for turn in reversed(self.conversation_history):
            if turn.intent == Intent.SEARCH and turn.search_results:
                return turn.search_results
        return self.current_articles if self.current_articles else None
    
    def get_article_by_reference(self, ref: str) -> Optional[Dict[str, Any]]:
        """
        Получить статью по ссылке ("первая", "2", "вторая статья").
        
        Args:
            ref: Ссылка на статью
            
        Returns:
            Словарь с данными статьи или None
        """
        articles = self.get_last_search_results()
        if not articles:
            return None
            
        # Числовые ссылки
        ref_lower = ref.lower().strip()
        
        # Попытка извлечь число
        number_words = {
            "первая": 1, "первую": 1, "первой": 1, "1": 1,
            "вторая": 2, "вторую": 2, "второй": 2, "2": 2,
            "третья": 3, "третью": 3, "третьей": 3, "3": 3,
            "четвёртая": 4, "четвертая": 4, "четвёртую": 4, "4": 4,
            "пятая": 5, "пятую": 5, "пятой": 5, "5": 5,
        }
        
        index = number_words.get(ref_lower)
        if index is None:
            # Попробовать извлечь число из строки
            import re
            match = re.search(r'\d+', ref_lower)
            if match:
                index = int(match.group())
        
        if index and 1 <= index <= len(articles):
            return articles[index - 1]
            
        return None
    
    def get_conversation_summary(self, max_turns: int = 5) -> str:
        """
        Получить краткое описание контекста для LLM.
        """
        lines = []
        
        if self.current_topic:
            lines.append(f"Текущая тема: {self.current_topic}")
            
        if self.current_articles:
            lines.append(f"В контексте {len(self.current_articles)} статей из последнего поиска")
            
        recent = self.get_recent_turns(max_turns)
        if recent:
            lines.append("Последние сообщения:")
            for turn in recent:
                lines.append(f"  User: {turn.user_message[:100]}...")
                if turn.bot_response:
                    lines.append(f"  Bot: {turn.bot_response[:100]}...")
                    
        return "\n".join(lines) if lines else "Новый диалог"
    
    def clear(self):
        """Очистить контекст."""
        self.conversation_history = []
        self.current_topic = None
        self.current_articles = []
        self.updated_at = datetime.now()
