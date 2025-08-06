from datetime import datetime, timedelta
from dataclasses import dataclass, field
from utils.nlu.intents import Intent
from utils.nlu.entities import Entity, EntityType
from typing import List, Dict, Any, Optional


@dataclass
class ConversationTurn:
    timestamp: datetime
    user_message: str
    intent: Intent
    entities: List[Entity]
    bot_response: Optional[str] = None
    search_results: Optional[List[str]] = None
    
@dataclass
class UserContext:
    user_id: int
    conversation_history: List[ConversationTurn] = field(default_factory=list)
    current_topic: Optional[str] = None
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    last_search_results: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_turn(self, turn: ConversationTurn):
        self.conversation_history.append(turn)
        self.updated_at = datetime.now()
        
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

    def get_recent_entities(self, entity: EntityType, hours: int = 24) -> List[Entity]:
        """Получает все сущности определенного типа из последних N часов разговора

        Args:
            entity (EntityType): Тип сущности для извлечения
            hours (int, optional): Количество часов для поиска. Defaults to 24.

        Returns:
            List[Entity]: Список найденных сущностей
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        entities = [] 
        for turn in self.conversation_history:
            if turn.timestamp >= cutoff_time:
                entities.extend(
                    [e for e in turn.entities if e.type == entity]
                )
        return entities
    
    def get_last_search_context(self) -> Optional[ConversationTurn]:
        """Получает последний запрос пользователя с результатами поиска

        Returns:
            Optional[ConversationTurn]: Последний запрос с результатами поиска или None
        """
        for turn in reversed(self.conversation_history):
            if turn.intent == Intent.SEARCH and turn.search_results:
                return turn
        return None
        
