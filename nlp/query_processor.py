from typing import Dict, Any
from utils.nlu.context import UserContext
from utils.nlu.intents import Intent, IntentResult
from utils.nlu.entities import EntityExtractionResult, EntityType
from .intent_classifier import RuleBasedIntentClassifier
from .entity_classifier import RuleBasedEntityExtractor
from dataclasses import dataclass

@dataclass
class QueryProcessingResult:
    """
    Результат обработки пользовательского запроса.
    
    Attributes:
        intent: IntentResult
            Результат классификации намерения
        entities: EntityExtractionResult
            Результат извлечения сущностей
        query_params: Dict[str, Any]
            Параметры для выполнения запроса
        response_type: str
            Тип ответа, который следует дать пользователю
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
        self.entity_classifier = RuleBasedEntityExtractor()

    async def process(self, text: str, context: UserContext) -> QueryProcessingResult:
        """
        Обрабатывает пользовательский запрос с учетом контекста.
        
        Args:
            text: Текст запроса пользователя
            context: Контекст пользователя для улучшения понимания
            
        Returns:
            QueryProcessingResult с результатами обработки
        """
        # Улучшаем текст запроса с учетом контекста
        enhanced_text = self._enhance_with_context(text, context)
        
        # Классифицируем намерение с учетом контекста
        last_intent = None
        if context.conversation_history:
            last_intent = context.conversation_history[-1].intent
        
        intent_result = self.intent_classifier.classify(enhanced_text, last_intent)
        
        # Извлекаем сущности (передаем намерение для контекстного извлечения)
        entities_result = await self.entity_classifier.extract(enhanced_text, intent_result.intent)
        
        # Дополняем сущности из контекста, если они отсутствуют
        entities_result = self._enrich_entities_from_context(entities_result, context, intent_result)
        
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
            elif entity.type.value == "url":
                params["url"] = entity.normalized_value or entity.value
            elif entity.type.value == "doi":
                params["doi"] = entity.normalized_value or entity.value
            elif entity.type.value == "arxiv_id":
                params["arxiv_id"] = entity.normalized_value or entity.value
            elif entity.type.value == "pubmed_id":
                params["pubmed_id"] = entity.normalized_value or entity.value
            elif entity.type.value == "ieee_id":
                params["ieee_id"] = entity.normalized_value or entity.value
        
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
            # Если нет явного идентификатора, оставим сырой текст (может содержать URL/ID)
            if not any(k in params for k in ["url", "doi", "arxiv_id", "pubmed_id", "ieee_id"]):
                params["query"] = entities.raw_text
        elif intent.intent == Intent.HELP:
            params["action"] = "help"
        elif intent.intent == Intent.GREETING:
            params["action"] = "greeting"
        
        return params
    
    def _enhance_with_context(self, text: str, context: UserContext) -> str:
        """
        Улучшает текст запроса с учетом контекста пользователя.
        Например, добавляет информацию о предыдущих запросах или текущем состоянии диалога.
        """
        # Если запрос очень короткий и есть контекст, можем добавить тему
        if len(text.split()) <= 3 and context.current_topic:
            # Для коротких запросов типа "еще статьи", "больше информации"
            if any(word in text.lower() for word in ['еще', 'больше', 'также', 'тоже']):
                text = f"{text} по {context.current_topic}"
        
        return text
    
    def _enrich_entities_from_context(self, entities: EntityExtractionResult, context: UserContext, intent: IntentResult) -> EntityExtractionResult:
        """
        Дополняет извлеченные сущности информацией из контекста диалога.
        """
        from utils.nlu.entities import Entity
        
        # Если это запрос на поиск и нет темы, но есть текущая тема в контексте
        if intent.intent == Intent.SEARCH:
            has_topic = any(e.type.value == "topic" for e in entities.entities)
            
            if not has_topic and context.current_topic:
                # Добавляем тему из контекста
                topic_entity = Entity(
                    type=EntityType.TOPIC,
                    value=context.current_topic,
                    confidence=0.7,  # Немного меньше уверенности для контекстных сущностей
                    start_pos=0,
                    end_pos=0
                )
                entities.entities.append(topic_entity)
            
            # Добавляем недавние авторы из истории, если нет автора в текущем запросе
            has_author = any(e.type.value == "author" for e in entities.entities)
            if not has_author:
                recent_authors = context.get_recent_entities(EntityType.AUTHOR, hours=1)
                if recent_authors:
                    # Берем последнего автора
                    last_author = recent_authors[-1]
                    author_entity = Entity(
                        type=EntityType.AUTHOR,
                        value=last_author.value,
                        confidence=0.6,
                        start_pos=0,
                        end_pos=0
                    )
                    entities.entities.append(author_entity)
        
        return entities
    
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

    
