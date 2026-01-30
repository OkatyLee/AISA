"""
NLU Pipeline - основной пайплайн обработки сообщений.

Объединяет классификацию намерений и извлечение сущностей.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from nlu.models import (
    Intent, IntentResult,
    Entity, EntityType, EntityExtractionResult,
    UserContext,
)
from nlu.classifiers import LLMIntentClassifier, LLMEntityExtractor
from nlu.context_manager import ContextManager
from utils.logger import setup_logger

logger = setup_logger(name="nlu_pipeline", level=logging.INFO)


@dataclass
class NLUResult:
    """
    Результат обработки сообщения NLU пайплайном.
    """
    intent: IntentResult
    entities: EntityExtractionResult
    query_params: Dict[str, Any]
    response_type: str
    needs_cloud_llm: bool = False
    
    def get_entity(self, entity_type: EntityType) -> Optional[Entity]:
        """Получить первую сущность определённого типа."""
        return self.entities.get_first(entity_type)


class NLUPipeline:
    """
    Главный пайплайн обработки естественного языка.
    
    Использует:
    - LLM-based классификатор намерений
    - LLM-based извлекатель сущностей
    - Менеджер контекста
    """
    
    def __init__(
        self,
        ollama_url: str = "http://ollama:11434",
        db_path: str = "db/scientific_assistant.db",
    ):
        self.intent_classifier = LLMIntentClassifier(ollama_url=ollama_url)
        self.entity_extractor = LLMEntityExtractor(ollama_url=ollama_url)
        self.context_manager = ContextManager(db_path=db_path)
        
    async def close(self):
        """Закрытие ресурсов."""
        await self.intent_classifier.close()
        await self.entity_extractor.close()
        await self.context_manager.close()
    
    async def process(
        self,
        user_id: int,
        message: str,
    ) -> NLUResult:
        """
        Обработать сообщение пользователя.
        
        Args:
            user_id: ID пользователя
            message: Текст сообщения
            
        Returns:
            NLUResult с результатами обработки
        """
        # Предобработка текста
        text = self._preprocess(message)
        
        # Получаем контекст
        context = await self.context_manager.get_context(user_id)
        
        # Классифицируем намерение и извлекаем сущности параллельно
        import asyncio
        intent_task = self.intent_classifier.classify(text, context)
        entities_task = self.entity_extractor.extract(text, context)
        
        intent_result, entities_result = await asyncio.gather(intent_task, entities_task)
        
        # Обогащаем сущности из контекста
        entities_result = self._enrich_from_context(entities_result, context, intent_result)
        
        # Формируем параметры запроса
        query_params = self._build_query_params(intent_result, entities_result, context)
        
        # Определяем тип ответа
        response_type = self._determine_response_type(intent_result)
        
        # Проверяем, нужна ли облачная LLM
        needs_cloud_llm = Intent.requires_cloud_llm(intent_result.intent)
        
        return NLUResult(
            intent=intent_result,
            entities=entities_result,
            query_params=query_params,
            response_type=response_type,
            needs_cloud_llm=needs_cloud_llm,
        )
    
    async def update_context(
        self,
        user_id: int,
        message: str,
        result: NLUResult,
        bot_response: Optional[str] = None,
        search_results: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Обновить контекст после обработки.
        
        Args:
            user_id: ID пользователя
            message: Сообщение пользователя
            result: Результат NLU
            bot_response: Ответ бота
            search_results: Результаты поиска
        """
        await self.context_manager.update_context(
            user_id=user_id,
            message=message,
            intent=result.intent.intent,
            entities=result.entities.entities,
            bot_response=bot_response,
            search_results=search_results,
        )
    
    def _preprocess(self, text: str) -> str:
        """Предобработка текста."""
        # Удаляем лишние пробелы
        text = re.sub(r'\s+', ' ', text.strip())
        return text
    
    def _enrich_from_context(
        self,
        entities: EntityExtractionResult,
        context: UserContext,
        intent: IntentResult,
    ) -> EntityExtractionResult:
        """Обогатить сущности из контекста."""
        
        # Для поиска: если нет темы, берём из контекста
        if intent.intent == Intent.SEARCH:
            if not entities.has_type(EntityType.TOPIC) and context.current_topic:
                entities.entities.append(Entity(
                    type=EntityType.TOPIC,
                    value=context.current_topic,
                    confidence=0.7,
                    normalized_value=context.current_topic,
                ))
        
        # Для работы со статьями: резолвим ссылки
        if intent.intent in {Intent.GET_SUMMARY, Intent.EXPLAIN, Intent.SAVE_ARTICLE}:
            article_ref = entities.get_first(EntityType.ARTICLE_REF)
            if article_ref and context.current_articles:
                article = context.get_article_by_reference(article_ref.value)
                if article:
                    # Добавляем информацию о статье
                    if article.get("doi"):
                        entities.entities.append(Entity(
                            type=EntityType.DOI,
                            value=article["doi"],
                            confidence=0.95,
                        ))
                    elif article.get("url"):
                        entities.entities.append(Entity(
                            type=EntityType.URL,
                            value=article["url"],
                            confidence=0.95,
                        ))
        
        return entities
    
    def _build_query_params(
        self,
        intent: IntentResult,
        entities: EntityExtractionResult,
        context: UserContext,
    ) -> Dict[str, Any]:
        """Построить параметры запроса."""
        params = entities.to_search_params()
        params["intent"] = intent.intent.value
        
        # Добавляем контекстные статьи для работы с ними
        if intent.intent in {Intent.GET_SUMMARY, Intent.EXPLAIN, Intent.COMPARE}:
            article_ref = entities.get_first(EntityType.ARTICLE_REF)
            if article_ref:
                article = context.get_article_by_reference(article_ref.value)
                if article:
                    params["article"] = article
            
            # Для сравнения может быть несколько статей
            if intent.intent == Intent.COMPARE:
                params["articles"] = context.current_articles
        
        # Для поиска формируем query
        if intent.intent == Intent.SEARCH:
            if not params.get("query"):
                topic = entities.get_first(EntityType.TOPIC)
                if topic:
                    params["query"] = topic.normalized_value or topic.value
                else:
                    # Извлекаем поисковую часть из текста
                    params["query"] = self._extract_search_query(entities.raw_text)
        
        return params
    
    def _extract_search_query(self, text: str) -> str:
        """
        Извлечь поисковый запрос из текста, убрав служебные слова.
        
        "найди статьи по vibe coding" -> "vibe coding"
        """
        import re
        text_lower = text.lower().strip()
        
        # Паттерны для удаления начала
        prefixes = [
            r'^(?:найди|найти|поищи|искать|ищи|покажи|дай)\s+(?:мне\s+)?(?:статьи?\s+)?(?:по\s+)?',
            r'^(?:статьи?\s+)?(?:по|про|на\s+тему)\s+',
            r'^поиск\s+(?:статей\s+)?(?:по\s+)?',
            r'^(?:хочу\s+)?(?:найти\s+)?(?:статьи?\s+)?(?:про|по|о)\s+',
        ]
        
        result = text_lower
        for pattern in prefixes:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        
        # Удаляем trailing служебные слова
        result = re.sub(r'\s+(?:статьи?|статей)\s*$', '', result)
        
        return result.strip() if result.strip() else text
    
    def _determine_response_type(self, intent: IntentResult) -> str:
        """Определить тип ответа."""
        response_types = {
            Intent.SEARCH: "search_results",
            Intent.SAVE_ARTICLE: "confirmation",
            Intent.LIST_LIBRARY: "article_list",
            Intent.GET_SUMMARY: "summary",
            Intent.EXPLAIN: "explanation",
            Intent.COMPARE: "comparison",
            Intent.DELETE_ARTICLE: "confirmation",
            Intent.HELP: "help_message",
            Intent.GREETING: "greeting_message",
            Intent.CHAT: "chat_response",
            Intent.UNKNOWN: "clarification",
        }
        return response_types.get(intent.intent, "default")
