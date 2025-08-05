from enum import Enum
from typing import List, Tuple
from attr import dataclass

class Intent(Enum):
    """
    Перечисление возможных намерений пользователя в системе.

    Attributes:
        SEARCH: Намерение искать статьи/информацию
        SAVE_ARTICLE: Намерение сохранить статью для последующего использования
        LIST_SAVED: Намерение перечислить все сохраненные статьи
        GET_SUMMARY: Намерение получить резюме статьи
        DELETE_ARTICLE: Намерение удалить сохраненную статью
        HELP: Намерение запросить помощь/информацию
        GREETING: Намерение поприветствовать систему/начать разговор
        FILTER_RESULTS: Намерение применить фильтры к результатам поиска
        GET_RECOMMENDATIONS: Намерение получить рекомендованные статьи
        UNKNOWN: Намерение по умолчанию, когда ввод пользователя не может быть классифицирован
    """
    SEARCH = "search"
    SAVE_ARTICLE = "save_article"
    LIST_SAVED = "list_saved"
    GET_SUMMARY = "get_summary"
    DELETE_ARTICLE = "delete_article"
    HELP = "help"
    GREETING = "greeting"
    FILTER_RESULTS = "filter_results"
    GET_RECOMMENDATIONS = "get_recommendations"
    UNKNOWN = "unknown"
    
@dataclass    
class IntentResult:
    """
    Результат классификации намерения пользователя.
    Attributes:
        intent: Определенное намерение пользователя
        confidence: Уверенность в классификации (от 0 до 1)
        alternatives: Альтернативные намерения с их уверенностью
    """
    intent: Intent
    confidence: float
    alternatives: List[Tuple[Intent, float]]