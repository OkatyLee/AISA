from aiogram import Dispatcher, F
from aiogram.types import Message
from config.messages import COMMAND_MESSAGES
from utils.validators import InputValidator
from nlp.query_processor import QueryProcessingResult, QueryProcessor
from nlp.context_manager import ContextManager
from utils.nlu.intents import Intent
from utils.logger import setup_logger
from utils.error_handler import ErrorHandler
from .search_commands import extract_search_filters

validator = InputValidator()
query_processor = QueryProcessor()
context_manager = ContextManager("db/scientific_assistant.db")
logger = setup_logger(__name__)

def register_message_handlers(dp: Dispatcher):
    
    dp.message.register(message_handler, F.text)

async def message_handler(message: Message):
    
    text = validator.sanitize_text(message.text)
    user_id = message.from_user.id

    if validator.contains_suspicious_content(text):
        await message.answer(
            "⚠️ Сообщение содержит потенциально небезопасный контент. "
            "Пожалуйста, будьте осторожны."
        )
        return

    # Получаем контекст пользователя
    try:
        user_context = await context_manager.get_user_context(user_id)
        
        # Обрабатываем запрос с помощью NLP с учетом контекста
        result = await query_processor.process(text, user_context)
        
        # Обрабатываем результат
        bot_response = await _handle_processed_query(message, result)
        
        # Обновляем контекст после обработки
        await context_manager.update_user_context(
            user_id=user_id,
            message=text,
            intent=result.intent.intent,
            entities=result.entities.entities,
            bot_response=bot_response,
            search_results=result.query_params.get('search_results', [])
        )
        
    except Exception as e:
        await ErrorHandler.handle_message_error(message, e, status_message=None)

async def _handle_processed_query(message: Message, result: QueryProcessingResult) -> str:
    """
    Обрабатывает результат NLP-анализа и отвечает пользователю.
    
    Returns:
        str: Текст ответа бота для сохранения в контекст
    """
    intent = result.intent.intent
    params = result.query_params
    
    if intent == Intent.SEARCH:
        return await _handle_search_intent(message, params)
    elif intent == Intent.GREETING:
        return await _handle_greeting_intent(message)
    elif intent == Intent.HELP:
        return await _handle_help_intent(message)
    elif intent == Intent.LIST_SAVED:
        return await _handle_list_saved_intent(message)
    elif intent == Intent.GET_SUMMARY:
        return await _handle_summary_intent(message, params)
    elif intent == Intent.UNKNOWN:
        return await _handle_unknown_intent(message, result)
    else:
        response = ("Я понял ваше намерение, но пока не умею это обрабатывать. "
                   "Попробуйте использовать команды или переформулируйте запрос.")
        await message.answer(response)
        return response

async def _handle_search_intent(message: Message, params: dict) -> str:
    """Обрабатывает намерение поиска.
    Args:
        message: Сообщение от пользователя
        params: Параметры запроса
    
    Returns:
        str: Текст ответа бота
    """
    print(params)
    try:
        if "query" in params:
            query = params["query"]
        elif "topic" in params:
            query = params["topic"]
        else:
            query = "машинное обучение"  # default query

        # Создаем фильтры из извлеченных сущностей
        filters = {}
        if "year" in params:
            filters["year"] = params["year"]
        if "author" in params:
            filters["author"] = params["author"]
        
        # Также извлекаем фильтры из текста запроса (синтаксис year:2023, author:"Name")
        original_query = query
        query, additional_filters = extract_search_filters(query)
        
        # Объединяем фильтры из сущностей и текста
        filters.update(additional_filters)
        
        # Формируем команду для поиска
        search_command_text = f"/search {query}"
        
        # Создаем контекстный ответ
        filter_info = ""
        if filters:
            filter_parts = []
            if "year" in filters:
                filter_parts.append(f"год: {filters['year']}")
            if "author" in filters:
                filter_parts.append(f"автор: {filters['author']}")
            filter_info = f" (фильтры: {', '.join(filter_parts)})"
        
        search_response = f"🔍 Ищу статьи по запросу: {query}{filter_info}"
        await message.answer(search_response)
        
        from .search_commands import search_command
        from services.search import SearchService
        from services.utils import SearchUtils
        
        # Выполняем поиск напрямую с фильтрами
        try:
            search_service = SearchService()
            results = await search_service.search_papers(query, limit=5, filters=filters)
            
            if not results or not any(result.success for result in results.values()):
                await SearchUtils._send_no_results_message(message, original_query)
                return search_response
            
            # Получаем сохраненные статьи пользователя для проверки
            saved_urls = await SearchUtils._get_user_saved_urls(message.from_user.id)
            aggregated_results = search_service.aggregate_results(results)
            
            # Отправляем результаты
            await SearchUtils._send_search_results(message, aggregated_results, query, saved_urls)
            
        except Exception as search_error:
            logger.error(f"Ошибка при поиске через NLP: {search_error}")
            # Fallback на обычную команду поиска
            message = message.model_copy(update={"text": search_command_text})
            await search_command(message)
        
        return search_response
        
    except Exception as e:
        error_response = "Произошла ошибка при поиске. Попробуйте позже."
        await ErrorHandler.handle_search_error(message, e)
        return error_response

async def _handle_greeting_intent(message: Message) -> str:
    """Обрабатывает приветствие."""
    response = (
        "👋 Привет! Я научный ассистент AISA.\n\n"
        "Я могу помочь вам:\n"
        "🔍 Найти научные статьи\n"
        "📚 Сохранить интересные статьи\n"
        "📝 Получить краткое содержание/анализ статей\n"
        "📊 Показать статистику\n\n"
        "Просто напишите мне, что вас интересует, или используйте команды!"
    )
    await message.answer(response)
    return response

async def _handle_help_intent(message: Message) -> str:
    """Обрабатывает запрос помощи."""
    response = COMMAND_MESSAGES.get("help_text", "Я могу помочь вам с поиском и сохранением статей. Вот список доступных команд:")
    await message.answer(response)
    return response
    response = COMMAND_MESSAGES.get("help_text", "Я могу помочь вам с поиском и сохранением статей. Вот список доступных команд:")
    await message.answer(response)

async def _handle_list_saved_intent(message: Message) -> str:
    """Обрабатывает запрос списка сохраненных статей."""
    try:
        from .commands import library_command
        await library_command(message)
        return "Показываю ваши сохраненные статьи"
        
    except Exception as e:
        error_response = "Ошибка при получении списка сохраненных статей"
        await ErrorHandler.handle_library_error(message, e)
        return error_response

async def _handle_summary_intent(message: Message, params: dict) -> str:
    """
    Обрабатывает запрос резюме.
    TODO: Реализовать логику получения резюме статьи. Пока заглушка
    """
    response = (
        "Пока функционал получения резюме статьи из общения с ботом не реализован. "
        "📝 Для получения резюме статьи найдите ее в библиотеке или в поиске /search."
    )
    await message.answer(response)
    return response

async def _handle_unknown_intent(message: Message, result) -> str:
    """Обрабатывает неопознанное намерение."""
    confidence = result.intent.confidence
    
    if confidence < 0.3:
        response = (
            "🤔 Я не совсем понял ваш запрос.\n\n"
            "Попробуйте:\n"
            "• Использовать команды (/help для справки)\n"
            "• Переформулировать запрос\n"
            "• Быть более конкретным\n\n"
            "Например: \"Найди статьи про machine learning\" или \"Мои сохраненные статьи\"\n"
            "Рекомендую использовать команды для более точных запросов.\n"
            "Ключевые слова и авторов лучше писать на английском языке."
        )
    else:
        # Если есть альтернативы с хорошей уверенностью
        alternatives = result.intent.alternatives
        if alternatives and alternatives[0][1] > 0.2:
            alt_intent = alternatives[0][0]
            response = f"🤔 Возможно, вы хотели: {_intent_to_text(alt_intent)}?\n"
            response += "Если да, переформулируйте запрос более четко."
        else:
            response = (
                "Я не уверен, что правильно понял ваш запрос. "
                "Попробуйте быть более конкретным или используйте команды."
            )
    
    await message.answer(response)
    return response

def _intent_to_text(intent: Intent) -> str:
    """Преобразует намерение в текстовое описание."""
    intent_texts = {
        Intent.SEARCH: "найти статьи",
        Intent.LIST_SAVED: "показать сохраненные статьи",
        Intent.HELP: "получить помощь",
        Intent.GREETING: "поприветствоваться",
        Intent.GET_SUMMARY: "получить резюме статьи"
    }
    return intent_texts.get(intent, "что-то другое")