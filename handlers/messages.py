from aiogram import Dispatcher, F
from aiogram.types import Message
from config.messages import COMMAND_MESSAGES
from utils.validators import InputValidator
from nlp.query_processor import QueryProcessingResult, QueryProcessor
from utils.nlu.intents import Intent
from utils.logger import setup_logger
from utils.error_handler import ErrorHandler

validator = InputValidator()
query_processor = QueryProcessor()
logger = setup_logger(__name__)

def register_message_handlers(dp: Dispatcher):
    
    dp.message.register(message_handler, F.text)

async def message_handler(message: Message):
    
    text = validator.sanitize_text(message.text)

    if validator.contains_suspicious_content(text):
        await message.answer(
            "⚠️ Сообщение содержит потенциально небезопасный контент. "
            "Пожалуйста, будьте осторожны."
        )
        return

    # Обрабатываем запрос с помощью NLP
    try:
        result = query_processor.process(text)
        await _handle_processed_query(message, result)
    except Exception as e:
        await ErrorHandler.handle_message_error(message, e, status_message=None)

async def _handle_processed_query(message: Message, result: QueryProcessingResult):
    """
    Обрабатывает результат NLP-анализа и отвечает пользователю.
    """
    intent = result.intent.intent
    params = result.query_params
    
    if intent == Intent.SEARCH:
        await _handle_search_intent(message, params)
    elif intent == Intent.GREETING:
        await _handle_greeting_intent(message)
    elif intent == Intent.HELP:
        await _handle_help_intent(message)
    elif intent == Intent.LIST_SAVED:
        await _handle_list_saved_intent(message)
    elif intent == Intent.GET_SUMMARY:
        await _handle_summary_intent(message, params)
    elif intent == Intent.UNKNOWN:
        await _handle_unknown_intent(message, result)
    else:
        await message.answer(
            "Я понял ваше намерение, но пока не умею это обрабатывать. "
            "Попробуйте использовать команды или переформулируйте запрос."
        )

async def _handle_search_intent(message: Message, params: dict):
    """Обрабатывает намерение поиска.
    Args:
        message: Сообщение от пользователя
        params: Параметры запроса
    """
    print(params)
    try:
        if "query" in params:
            query = params["query"]
        elif "topic" in params:
            query = params["topic"]
        else:
            query = "машинное обучение"  # default query

        from .search_commands import search_command
        message = message.model_copy(update={"text": f"/search {query}"})  # Подготавливаем текст команды
        await search_command(message)
        
    except Exception as e:
        await ErrorHandler.handle_search_error(message, e)

async def _handle_greeting_intent(message: Message):
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

async def _handle_help_intent(message: Message):
    """Обрабатывает запрос помощи."""
    response = COMMAND_MESSAGES.get("help_text", "Я могу помочь вам с поиском и сохранением статей. Вот список доступных команд:")
    await message.answer(response)

async def _handle_list_saved_intent(message: Message):
    """Обрабатывает запрос списка сохраненных статей."""
    try:
        from .commands import library_command
        await library_command(message)
        
    except Exception as e:
        await ErrorHandler.handle_library_error(message, e)

async def _handle_summary_intent(message: Message, params: dict):
    """
    Обрабатывает запрос резюме.
    TODO: Реализовать логику получения резюме статьи. Пока заглушка
    """
    await message.answer(
        "Пока функционал получения резюме статьи из общения с ботом не реализован."
        "📝 Для получения резюме статьи найдите ее в библиотеке или в поиске /search."
    )

async def _handle_unknown_intent(message: Message, result):
    """Обрабатывает неопознанное намерение."""
    confidence = result.intent.confidence
    
    if confidence < 0.3:
        response = (
            "🤔 Я не совсем понял ваш запрос.\n\n"
            "Попробуйте:\n"
            "• Использовать команды (/help для справки)\n"
            "• Переформулировать запрос\n"
            "• Быть более конкретным\n\n"
            "Например: \"Найди статьи про machine learning\" или \"Мои сохраненные статьи\""
            "Рекомендую использовать команды для более точных запросов."
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