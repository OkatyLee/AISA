"""Intent models for NLU."""

from enum import Enum
from typing import List, Tuple, Optional
from dataclasses import dataclass


class Intent(Enum):
    """
    Перечисление возможных намерений пользователя.

    Attributes:
        SEARCH: Поиск статей/информации
        SAVE_ARTICLE: Сохранение статьи в библиотеку
        LIST_LIBRARY: Просмотр библиотеки/сохранённых статей
        GET_SUMMARY: Получение резюме статьи (требует OpenRouter)
        EXPLAIN: Объяснение чего-то по статье (требует OpenRouter)
        COMPARE: Сравнение нескольких статей (требует OpenRouter)
        DELETE_ARTICLE: Удаление статьи из библиотеки
        HELP: Запрос помощи
        GREETING: Приветствие
        CHAT: Обычный разговор (не требует действий)
        UNKNOWN: Не удалось определить намерение
    """
    SEARCH = "search"
    SAVE_ARTICLE = "save_article"
    LIST_LIBRARY = "list_library"
    GET_SUMMARY = "get_summary"
    EXPLAIN = "explain"
    COMPARE = "compare"
    DELETE_ARTICLE = "delete_article"
    HELP = "help"
    GREETING = "greeting"
    CHAT = "chat"
    UNKNOWN = "unknown"
    
    @classmethod
    def requires_cloud_llm(cls, intent: "Intent") -> bool:
        """Проверяет, требует ли намерение облачную LLM (OpenRouter)."""
        return intent in {cls.GET_SUMMARY, cls.EXPLAIN, cls.COMPARE}
    
    @classmethod
    def requires_action(cls, intent: "Intent") -> bool:
        """Проверяет, требует ли намерение выполнения действия."""
        return intent in {
            cls.SEARCH, 
            cls.SAVE_ARTICLE, 
            cls.LIST_LIBRARY, 
            cls.GET_SUMMARY,
            cls.EXPLAIN,
            cls.COMPARE,
            cls.DELETE_ARTICLE,
            cls.HELP,
        }


@dataclass
class IntentResult:
    """
    Результат классификации намерения.
    
    Attributes:
        intent: Определённое намерение
        confidence: Уверенность (0.0 - 1.0)
        alternatives: Альтернативные намерения с их уверенностью
        raw_response: Сырой ответ от LLM (для отладки)
    """
    intent: Intent
    confidence: float
    alternatives: List[Tuple[Intent, float]]
    raw_response: Optional[str] = None
    
    def is_confident(self, threshold: float = 0.7) -> bool:
        """Проверяет, достаточно ли высокая уверенность."""
        return self.confidence >= threshold
