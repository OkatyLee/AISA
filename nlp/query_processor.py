from typing import Dict, Any
from utils.nlu.intents import Intent, IntentResult
from utils.nlu.entities import EntityExtractionResult
from .intent_classifier import RuleBasedIntentClassifier
from .entity_classifier import RuleBasedEntityClassifier
from attr import dataclass

@dataclass
class QueryProcessingResult:
    """
    Результат обработки пользовательского запроса.
    
    Attributes:
        intent: Результат классификации намерения
        entities: Результат извлечения сущностей
        query_params: Параметры для выполнения запроса
        response_type: Тип ответа, который следует дать пользователю
    """
    intent: IntentResult
    entities: EntityExtractionResult
    query_params: Dict[str, Any]
    response_type: str

class QueryProcessor:
    """
    Основной процессор пользовательских запросов.
    Объединяет классификацию намерений и извлечение сущностей.
    """
    
    def __init__(self):
        self.intent_classifier = RuleBasedIntentClassifier()
        self.entity_classifier = RuleBasedEntityClassifier()
    
    def process(self, text: str) -> QueryProcessingResult:
        """
        Обрабатывает пользовательский запрос.
        
        Args:
            text: Текст запроса пользователя
            
        Returns:
            QueryProcessingResult с результатами обработки
        """
        # Классифицируем намерение
        intent_result = self.intent_classifier.classify(text)
        
        # Извлекаем сущности
        entities_result = self.entity_classifier.classify(text)
        
        # Формируем параметры запроса на основе намерения и сущностей
        query_params = self._build_query_params(intent_result, entities_result)
        
        # Определяем тип ответа
        response_type = self._determine_response_type(intent_result)
        
        return QueryProcessingResult(
            intent=intent_result,
            entities=entities_result,
            query_params=query_params,
            response_type=response_type
        )
    
    def _build_query_params(self, intent: IntentResult, entities: EntityExtractionResult) -> Dict[str, Any]:
        """
        Строит параметры запроса на основе намерения и сущностей.
        """
        params = {}
        
        # Обрабатываем сущности
        for entity in entities.entities:
            if entity.type.value == "topic":
                params["topic"] = entity.value
            elif entity.type.value == "author":
                params["author"] = entity.value
            elif entity.type.value == "year":
                params["year"] = entity.value
            elif entity.type.value == "citation_count":
                params["min_citations"] = entity.value
            elif entity.type.value == "journal":
                params["journal"] = entity.value
        
        # Дополнительные параметры в зависимости от намерения
        if intent.intent == Intent.SEARCH:
            params["action"] = "search"
            # Если не указаны конкретные параметры, используем весь текст как поисковый запрос
            if not any(key in params for key in ["author", "topic", "year"]):
                params["query"] = entities.raw_text
        elif intent.intent == Intent.SAVE_ARTICLE:
            params["action"] = "save"
        elif intent.intent == Intent.LIST_SAVED:
            params["action"] = "list_saved"
        elif intent.intent == Intent.GET_SUMMARY:
            params["action"] = "summary"
        elif intent.intent == Intent.HELP:
            params["action"] = "help"
        elif intent.intent == Intent.GREETING:
            params["action"] = "greeting"
        
        return params
    
    def _determine_response_type(self, intent: IntentResult) -> str:
        """
        Определяет тип ответа на основе намерения.
        """
        response_types = {
            Intent.SEARCH: "search_results",
            Intent.SAVE_ARTICLE: "confirmation",
            Intent.LIST_SAVED: "article_list",
            Intent.GET_SUMMARY: "summary",
            Intent.HELP: "help_message",
            Intent.GREETING: "greeting_message",
            Intent.UNKNOWN: "clarification"
        }
        
        return response_types.get(intent.intent, "default")
