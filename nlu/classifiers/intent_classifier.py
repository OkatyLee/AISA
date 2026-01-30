"""
LLM-based Intent Classifier.

Классификатор намерений на базе локальной LLM (Ollama).
"""

import json
import logging
import re
from typing import Optional, List, Tuple

from services.llm.client import OllamaClient, ChatMessage
from nlu.models import Intent, IntentResult, UserContext
from utils.logger import setup_logger

logger = setup_logger(name="intent_classifier", level=logging.INFO)


INTENT_CLASSIFICATION_PROMPT = """Ты — классификатор намерений пользователя для научного ассистента.

Определи намерение пользователя из списка:
- search: поиск статей/информации ("найди статьи про...", "что есть по теме...")
- save_article: сохранить статью ("сохрани", "добавь в библиотеку")
- list_library: показать сохранённые статьи ("мои статьи", "что у меня есть", "покажи библиотеку")
- get_summary: суммаризация/резюме статьи ("сделай резюме", "проанализируй статью")
- explain: объяснить что-то по статье ("объясни", "что значит", "расскажи подробнее")
- compare: сравнить статьи ("сравни", "чем отличаются")
- delete_article: удалить статью ("удали", "убери из библиотеки")
- help: помощь ("помощь", "что ты умеешь")
- greeting: приветствие ("привет", "здравствуй")
- chat: обычный разговор (не требует действий)
- unknown: не удалось определить

{context}

Ответь ТОЛЬКО в формате JSON:
{{"intent": "название_намерения", "confidence": 0.0-1.0, "reasoning": "краткое объяснение"}}"""


class LLMIntentClassifier:
    """
    Классификатор намерений на базе LLM.
    
    Использует локальную модель (Ollama) для быстрой классификации.
    """
    
    def __init__(
        self,
        ollama_url: str = "http://ollama:11434",
        model: str = None,
    ):
        self.llm = OllamaClient(base_url=ollama_url, model=model)
        
    async def close(self):
        await self.llm.close()
    
    async def classify(
        self,
        text: str,
        context: Optional[UserContext] = None,
    ) -> IntentResult:
        """
        Классифицировать намерение пользователя.
        
        Args:
            text: Текст сообщения
            context: Контекст диалога
            
        Returns:
            IntentResult с определённым намерением
        """
        # Формируем контекст
        context_str = ""
        if context:
            if context.current_topic:
                context_str += f"\nТекущая тема диалога: {context.current_topic}"
            if context.current_articles:
                context_str += f"\nВ контексте {len(context.current_articles)} статей из последнего поиска"
            recent = context.get_recent_turns(2)
            if recent:
                context_str += "\nПоследние сообщения:"
                for turn in recent:
                    context_str += f"\n- User: {turn.user_message[:100]}"
        
        if context_str:
            context_str = f"\nКонтекст диалога:{context_str}"
        
        system_prompt = INTENT_CLASSIFICATION_PROMPT.format(context=context_str)
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=f"Сообщение пользователя: {text}"),
        ]
        
        try:
            # Проверяем доступность Ollama
            if not await self.llm.is_available():
                logger.warning("Ollama недоступна, используем fallback")
                return self._fallback_classify(text)
            
            response = await self.llm.chat(messages, temperature=0.1, max_tokens=200)
            return self._parse_response(response.content, text)
            
        except Exception as e:
            logger.error(f"Ошибка классификации: {e}")
            return self._fallback_classify(text)
    
    def _parse_response(self, response: str, original_text: str) -> IntentResult:
        """Парсинг ответа от LLM."""
        try:
            # Извлекаем JSON из ответа
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                intent_str = data.get("intent", "unknown")
                confidence = float(data.get("confidence", 0.5))
                
                # Преобразуем строку в Intent
                try:
                    intent = Intent(intent_str)
                except ValueError:
                    intent = Intent.UNKNOWN
                    confidence = 0.3
                
                return IntentResult(
                    intent=intent,
                    confidence=confidence,
                    alternatives=[],
                    raw_response=response,
                )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Ошибка парсинга ответа: {e}")
        
        return IntentResult(
            intent=Intent.UNKNOWN,
            confidence=0.3,
            alternatives=[],
            raw_response=response,
        )
    
    def _fallback_classify(self, text: str) -> IntentResult:
        """
        Fallback классификация на основе простых правил.
        Используется когда LLM недоступна.
        """
        text_lower = text.lower().strip()
        
        # Приветствия
        greetings = ["привет", "здравствуй", "hello", "hi", "добрый день", "добрый вечер"]
        if any(g in text_lower for g in greetings):
            return IntentResult(Intent.GREETING, 0.9, [])
        
        # Помощь
        help_words = ["помощь", "help", "что умеешь", "как работать"]
        if any(h in text_lower for h in help_words):
            return IntentResult(Intent.HELP, 0.9, [])
        
        # Поиск
        search_words = ["найди", "найти", "поиск", "ищи", "статьи про", "search"]
        if any(s in text_lower for s in search_words):
            return IntentResult(Intent.SEARCH, 0.8, [])
        
        # Библиотека
        library_words = ["мои статьи", "библиотека", "сохранённые", "покажи мои"]
        if any(l in text_lower for l in library_words):
            return IntentResult(Intent.LIST_LIBRARY, 0.8, [])
        
        # Суммаризация
        summary_words = ["резюме", "суммар", "анализ", "summary"]
        if any(s in text_lower for s in summary_words):
            return IntentResult(Intent.GET_SUMMARY, 0.8, [])
        
        # Сравнение
        compare_words = ["сравни", "сравнить", "compare"]
        if any(c in text_lower for c in compare_words):
            return IntentResult(Intent.COMPARE, 0.8, [])
        
        # Объяснение
        explain_words = ["объясни", "расскажи", "что значит", "что такое"]
        if any(e in text_lower for e in explain_words):
            return IntentResult(Intent.EXPLAIN, 0.7, [])
        
        # Сохранение
        save_words = ["сохрани", "добавь", "save"]
        if any(s in text_lower for s in save_words):
            return IntentResult(Intent.SAVE_ARTICLE, 0.7, [])
        
        # По умолчанию — это может быть поиск или чат
        if len(text.split()) <= 3:
            return IntentResult(Intent.SEARCH, 0.5, [(Intent.CHAT, 0.3)])
        
        return IntentResult(Intent.CHAT, 0.5, [(Intent.SEARCH, 0.3)])
