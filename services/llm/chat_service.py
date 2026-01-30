"""
Chat Service - сервис для общения в чате.

Роутинг:
- Обычные запросы → локальная LLM (Ollama)
- Объяснение по статье → облачная LLM (OpenRouter)
"""

import logging
from typing import Optional, List, Dict, Any, AsyncIterator

from .client import OllamaClient, OpenRouterClient, ChatMessage, LLMResponse
from nlu.models import Intent, UserContext
from utils.logger import setup_logger

logger = setup_logger(name="chat_service", level=logging.INFO)


# Системный промпт для ассистента
SYSTEM_PROMPT = """Ты — научный ассистент AISA (AI Scientific Assistant). Помогаешь пользователям искать и анализировать научные статьи.

Твои возможности:
- Поиск научных статей по теме, автору, году публикации
- Показ сохранённых статей в библиотеке пользователя
- Суммаризация и анализ статей
- Сравнение нескольких статей
- Объяснение научных концепций

Правила:
- Отвечай кратко и по делу
- Используй русский язык
- Если пользователь хочет найти статью — предложи уточнить тему или автора
- Если пользователь ссылается на статью из списка ("первая", "вторая") — используй контекст диалога
- Не выдумывай информацию о статьях — работай только с тем, что есть в контексте

{context}"""


class ChatService:
    """
    Сервис для общения в чате с роутингом между LLM.
    """
    
    def __init__(
        self,
        ollama_url: str = "http://ollama:11434",
        ollama_model: str = None,
    ):
        self.local_llm = OllamaClient(base_url=ollama_url, model=ollama_model)
        self.cloud_llm = OpenRouterClient()
        self._initialized = False
        
    async def initialize(self):
        """Инициализация сервиса."""
        if self._initialized:
            return
            
        # Проверяем доступность Ollama
        if await self.local_llm.is_available():
            await self.local_llm.ensure_model()
            logger.info("Локальная LLM (Ollama) готова")
        else:
            logger.warning("Локальная LLM недоступна, будет использоваться только облачная")
            
        self._initialized = True
    
    async def close(self):
        """Закрытие сервиса."""
        await self.local_llm.close()
        await self.cloud_llm.close()
    
    async def chat(
        self,
        user_message: str,
        context: Optional[UserContext] = None,
        use_cloud: bool = False,
        article_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Обработать сообщение пользователя.
        
        Args:
            user_message: Сообщение от пользователя
            context: Контекст диалога (НЕ влияет на выбор LLM)
            use_cloud: Принудительно использовать облачную LLM
            article_context: Контекст статьи (НЕ влияет на выбор LLM, только добавляет в промпт)
            
        Returns:
            Ответ от LLM
            
        Note:
            Облачная LLM используется ТОЛЬКО если явно указан use_cloud=True.
            Наличие article_context или context НЕ переключает на облачную LLM —
            это экономит ресурсы. Для тяжёлых задач (суммаризация, сравнение)
            используйте PaperService, который явно работает с облачной LLM.
        """
        await self.initialize()
        
        # Формируем системный промпт с контекстом
        context_str = ""
        if context:
            # Добавляем только краткую сводку, без статей
            context_str = f"\n\nКонтекст диалога:\n{context.get_conversation_summary(max_turns=3)}"
            
        if article_context:
            # Краткий контекст статьи для справки (не для глубокого анализа)
            context_str += f"\n\nТекущая статья: {article_context.get('title', 'Неизвестно')}"
            authors = article_context.get('authors', [])
            if authors:
                context_str += f" ({', '.join(authors[:2])}{'...' if len(authors) > 2 else ''})"
        
        system_prompt = SYSTEM_PROMPT.format(context=context_str)
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]
        
        # Добавляем историю диалога (последние 3 хода, без search_results для экономии токенов)
        if context:
            history_messages = []
            for turn in context.get_recent_turns(3):
                history_messages.append(
                    ChatMessage(role="user", content=turn.user_message)
                )
                if turn.bot_response:
                    # Ограничиваем длину предыдущих ответов
                    response_text = turn.bot_response[:500] + "..." if len(turn.bot_response) > 500 else turn.bot_response
                    history_messages.append(
                        ChatMessage(role="assistant", content=response_text)
                    )
            # Вставляем историю перед текущим сообщением
            messages = [messages[0]] + history_messages + [messages[1]]
        
        # Выбираем LLM — только по явному флагу use_cloud
        if use_cloud:
            # Используем облачную LLM только когда явно запрошено
            try:
                response = await self.cloud_llm.chat(messages, temperature=0.3)
                return response.content
            except Exception as e:
                logger.error(f"Ошибка облачной LLM: {e}")
                # Fallback на локальную
                if await self.local_llm.is_available():
                    response = await self.local_llm.chat(messages, temperature=0.7)
                    return response.content
                raise
        else:
            # По умолчанию — локальная LLM
            try:
                if await self.local_llm.is_available():
                    response = await self.local_llm.chat(messages, temperature=0.7)
                    return response.content
                else:
                    # Fallback на облачную только если локальная недоступна
                    logger.warning("Локальная LLM недоступна, используем облачную")
                    response = await self.cloud_llm.chat(messages, temperature=0.7)
                    return response.content
            except Exception as e:
                logger.error(f"Ошибка LLM: {e}")
                raise
    
    async def chat_stream(
        self,
        user_message: str,
        context: Optional[UserContext] = None,
        use_cloud: bool = False,
        article_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        Стриминг ответа от LLM.
        
        Yields:
            Чанки текста по мере генерации
        """
        await self.initialize()
        
        # Формируем системный промпт
        context_str = ""
        if context:
            context_str = f"\n\nКонтекст диалога:\n{context.get_conversation_summary(max_turns=3)}"
            
        if article_context:
            context_str += f"\n\nТекущая статья: {article_context.get('title', 'Неизвестно')}"
        
        system_prompt = SYSTEM_PROMPT.format(context=context_str)
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]
        
        # Добавляем историю
        if context:
            history_messages = []
            for turn in context.get_recent_turns(3):
                history_messages.append(ChatMessage(role="user", content=turn.user_message))
                if turn.bot_response:
                    response_text = turn.bot_response[:500] + "..." if len(turn.bot_response) > 500 else turn.bot_response
                    history_messages.append(ChatMessage(role="assistant", content=response_text))
            messages = [messages[0]] + history_messages + [messages[1]]
        
        # Выбираем LLM
        try:
            if use_cloud:
                async for chunk in self.cloud_llm.chat_stream(messages, temperature=0.3):
                    yield chunk
            else:
                if await self.local_llm.is_available():
                    async for chunk in self.local_llm.chat_stream(messages, temperature=0.7):
                        yield chunk
                else:
                    logger.warning("Локальная LLM недоступна, используем облачную")
                    async for chunk in self.cloud_llm.chat_stream(messages, temperature=0.7):
                        yield chunk
        except Exception as e:
            logger.error(f"Ошибка streaming: {e}")
            yield f"❌ Ошибка: {str(e)}"
    
    async def generate_action_response(
        self,
        intent: Intent,
        action_result: Any,
        user_message: str,
    ) -> str:
        """
        Генерировать ответ на основе выполненного действия.
        
        Args:
            intent: Намерение пользователя
            action_result: Результат выполнения действия
            user_message: Исходное сообщение пользователя
            
        Returns:
            Сформулированный ответ
        """
        # Для простых случаев можно возвращать шаблонные ответы
        if intent == Intent.GREETING:
            return "Привет! 👋 Я научный ассистент AISA. Помогу найти и проанализировать научные статьи. Что вас интересует?"
        
        if intent == Intent.HELP:
            return """🔬 **Как я могу помочь:**

**Поиск статей:**
- "Найди статьи про машинное обучение"
- "Статьи автора Hinton за 2023 год"

**Работа с библиотекой:**
- "Покажи мои сохранённые статьи"
- "Добавь эту статью в библиотеку"

**Анализ статей:**
- "Сделай резюме первой статьи"
- "Сравни эти две статьи"
- "Объясни, что такое трансформеры"

Просто напишите, что вас интересует! 📚"""
        
        if intent == Intent.LIST_LIBRARY:
            if not action_result:
                return "📚 Ваша библиотека пуста. Найдите интересные статьи и сохраните их!"
            # Результат будет отформатирован отдельно
            return None
        
        # Для сложных случаев используем LLM
        return None
