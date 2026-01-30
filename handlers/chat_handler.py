"""
Chat Handler - обработчик сообщений с NLU и LLM.

Основной хендлер для общения в чате, использующий:
- NLU Pipeline для понимания запросов
- Chat Service для генерации ответов
- Paper Service для анализа статей
"""

import logging
from typing import Optional, Dict, Any

from aiogram import Dispatcher, F
from aiogram.types import Message

from nlu import NLUPipeline, Intent
from nlu.models import EntityType
from nlu.pipeline import NLUResult
from services.llm import ChatService, PaperService
from utils.validators import InputValidator
from utils.logger import setup_logger

logger = setup_logger(name="chat_handler", level=logging.DEBUG)

# Глобальные сервисы (инициализируются при старте)
_nlu_pipeline: Optional[NLUPipeline] = None
_chat_service: Optional[ChatService] = None
_paper_service: Optional[PaperService] = None
_validator = InputValidator()


async def init_chat_services(
    ollama_url: str = "http://ollama:11434",
    db_path: str = "db/scientific_assistant.db",
):
    """Инициализация сервисов чата."""
    global _nlu_pipeline, _chat_service, _paper_service
    
    _nlu_pipeline = NLUPipeline(ollama_url=ollama_url, db_path=db_path)
    _chat_service = ChatService(ollama_url=ollama_url)
    _paper_service = PaperService()
    
    await _chat_service.initialize()
    logger.info("Chat services initialized")


async def close_chat_services():
    """Закрытие сервисов."""
    global _nlu_pipeline, _chat_service, _paper_service
    
    if _nlu_pipeline:
        await _nlu_pipeline.close()
    if _chat_service:
        await _chat_service.close()
    if _paper_service:
        await _paper_service.close()
        
    logger.info("Chat services closed")


def register_chat_handler(dp: Dispatcher):
    """Регистрация обработчика сообщений."""
    dp.message.register(handle_message, F.text)


async def handle_message(message: Message):
    """
    Главный обработчик текстовых сообщений.
    """
    global _nlu_pipeline, _chat_service, _paper_service
    
    # Ленивая инициализация
    if _nlu_pipeline is None:
        await init_chat_services()
    
    text = _validator.sanitize_text(message.text)
    user_id = message.from_user.id
    
    # Проверка на подозрительный контент
    if _validator.contains_suspicious_content(text):
        await message.answer(
            "⚠️ Сообщение содержит потенциально небезопасный контент."
        )
        return
    
    try:
        # Обрабатываем сообщение через NLU
        result = await _nlu_pipeline.process(user_id, text)
        
        logger.debug(
            f"NLU Result: intent={result.intent.intent.value}, "
            f"confidence={result.intent.confidence:.2f}, "
            f"entities={[e.type.value for e in result.entities.entities]}"
        )
        
        # Обрабатываем намерение
        bot_response = await _handle_intent(message, result)
        
        # Обновляем контекст
        await _nlu_pipeline.update_context(
            user_id=user_id,
            message=text,
            result=result,
            bot_response=bot_response,
        )
        
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке сообщения. Попробуйте ещё раз."
        )


async def _handle_intent(message: Message, result: NLUResult) -> str:
    """Обработка намерения и генерация ответа."""
    intent = result.intent.intent
    params = result.query_params
    
    handlers = {
        Intent.GREETING: _handle_greeting,
        Intent.HELP: _handle_help,
        Intent.SEARCH: _handle_search,
        Intent.LIST_LIBRARY: _handle_list_library,
        Intent.SAVE_ARTICLE: _handle_save_article,
        Intent.GET_SUMMARY: _handle_summary,
        Intent.EXPLAIN: _handle_explain,
        Intent.COMPARE: _handle_compare,
        Intent.CHAT: _handle_chat,
        Intent.UNKNOWN: _handle_unknown,
    }
    
    handler = handlers.get(intent, _handle_unknown)
    return await handler(message, result)


async def _handle_greeting(message: Message, result: NLUResult) -> str:
    """Обработка приветствия."""
    response = await _chat_service.generate_action_response(
        Intent.GREETING, None, message.text
    )
    await message.answer(response)
    return response


async def _handle_help(message: Message, result: NLUResult) -> str:
    """Обработка запроса помощи."""
    response = await _chat_service.generate_action_response(
        Intent.HELP, None, message.text
    )
    await message.answer(response)
    return response


async def _handle_search(message: Message, result: NLUResult) -> str:
    """Обработка поиска статей."""
    # Импортируем существующий поиск
    from handlers.search_commands import perform_search
    
    query = result.query_params.get("query", message.text)
    filters = {}
    
    if result.entities.has_type(EntityType.YEAR):
        year_entity = result.entities.get_first(EntityType.YEAR)
        filters["year"] = year_entity.normalized_value
        
    if result.entities.has_type(EntityType.AUTHOR):
        author_entity = result.entities.get_first(EntityType.AUTHOR)
        filters["author"] = author_entity.normalized_value
        
    if result.entities.has_type(EntityType.SOURCE):
        source_entity = result.entities.get_first(EntityType.SOURCE)
        filters["source"] = source_entity.normalized_value
    
    # Выполняем поиск
    try:
        await perform_search(message, query, filters)
        return f"Поиск по запросу: {query}"
    except Exception as e:
        logger.error(f"Search error: {e}")
        response = f"🔍 Ищу статьи по запросу: {query}\n\n❌ Произошла ошибка при поиске."
        await message.answer(response)
        return response


async def _handle_list_library(message: Message, result: NLUResult) -> str:
    """Показать библиотеку пользователя."""
    # Используем существующую команду
    from handlers.commands import show_library
    
    try:
        await show_library(message)
        return "Показываю библиотеку"
    except Exception as e:
        logger.error(f"Library error: {e}")
        response = "❌ Ошибка при загрузке библиотеки"
        await message.answer(response)
        return response


async def _handle_save_article(message: Message, result: NLUResult) -> str:
    """Сохранить статью."""
    context = await _nlu_pipeline.context_manager.get_context(message.from_user.id)
    
    # Ищем ссылку на статью
    article_ref = result.entities.get_first(EntityType.ARTICLE_REF)
    if article_ref:
        article = context.get_article_by_reference(article_ref.value)
        if article:
            # TODO: Реализовать сохранение статьи
            response = f"✅ Статья «{article.get('title', 'Без названия')}» сохранена в библиотеку!"
            await message.answer(response)
            return response
    
    response = "❓ Укажите, какую статью сохранить. Например: «сохрани первую статью»"
    await message.answer(response)
    return response


async def _handle_summary(message: Message, result: NLUResult) -> str:
    """Суммаризация статьи."""
    global _paper_service
    
    context = await _nlu_pipeline.context_manager.get_context(message.from_user.id)
    article = result.query_params.get("article")
    
    if not article:
        # Пробуем взять первую статью из контекста
        article_ref = result.entities.get_first(EntityType.ARTICLE_REF)
        if article_ref:
            article = context.get_article_by_reference(article_ref.value)
        elif context.current_articles:
            article = context.current_articles[0]
    
    if not article:
        response = "❓ Какую статью проанализировать? Сначала найдите статьи или укажите номер."
        await message.answer(response)
        return response
    
    # Показываем, что работаем
    await message.answer(f"📝 Анализирую статью: {article.get('title', 'Без названия')}...")
    
    try:
        summary = await _paper_service.summarize(article, detailed=True)
        
        # Генерируем PDF
        pdf_bytes = await _paper_service.generate_pdf_report(
            summary,
            title=f"Анализ: {article.get('title', 'Статья')}"
        )
        
        # Отправляем и текст, и PDF
        # Ограничиваем длину текста для Telegram
        if len(summary) > 4000:
            await message.answer(summary[:4000] + "\n\n_(продолжение в PDF)_", parse_mode="Markdown")
        else:
            await message.answer(summary, parse_mode="Markdown")
        
        # Отправляем PDF
        from aiogram.types import BufferedInputFile
        pdf_file = BufferedInputFile(
            pdf_bytes.read(),
            filename=f"analysis_{article.get('id', 'article')}.pdf"
        )
        await message.answer_document(pdf_file, caption="📄 Полный анализ в PDF")
        
        return f"Суммаризация: {article.get('title', '')}"
        
    except Exception as e:
        logger.error(f"Summary error: {e}", exc_info=True)
        response = "❌ Ошибка при анализе статьи. Попробуйте позже."
        await message.answer(response)
        return response


async def _handle_explain(message: Message, result: NLUResult) -> str:
    """Объяснение по статье."""
    global _paper_service
    
    context = await _nlu_pipeline.context_manager.get_context(message.from_user.id)
    article = result.query_params.get("article")
    
    if not article and context.current_articles:
        article = context.current_articles[0]
    
    try:
        explanation = await _paper_service.explain(
            message.text,
            paper=article,
        )
        
        await message.answer(explanation, parse_mode="Markdown")
        return f"Объяснение: {message.text[:50]}"
        
    except Exception as e:
        logger.error(f"Explain error: {e}")
        response = "❌ Ошибка при генерации объяснения."
        await message.answer(response)
        return response


async def _handle_compare(message: Message, result: NLUResult) -> str:
    """Сравнение статей."""
    global _paper_service
    
    articles = result.query_params.get("articles", [])
    
    if len(articles) < 2:
        response = "❓ Для сравнения нужно минимум 2 статьи. Сначала выполните поиск."
        await message.answer(response)
        return response
    
    await message.answer(f"⚖️ Сравниваю {len(articles)} статей...")
    
    try:
        comparison = await _paper_service.compare(articles)
        
        # Генерируем PDF
        pdf_bytes = await _paper_service.generate_pdf_report(
            comparison,
            title="Сравнительный анализ статей"
        )
        
        if len(comparison) > 4000:
            await message.answer(comparison[:4000] + "\n\n_(продолжение в PDF)_", parse_mode="Markdown")
        else:
            await message.answer(comparison, parse_mode="Markdown")
        
        from aiogram.types import BufferedInputFile
        pdf_file = BufferedInputFile(
            pdf_bytes.read(),
            filename="comparison_analysis.pdf"
        )
        await message.answer_document(pdf_file, caption="📄 Полный анализ в PDF")
        
        return "Сравнение статей"
        
    except Exception as e:
        logger.error(f"Compare error: {e}")
        response = "❌ Ошибка при сравнении статей."
        await message.answer(response)
        return response


async def _handle_chat(message: Message, result: NLUResult) -> str:
    """Обычный чат."""
    global _chat_service
    
    context = await _nlu_pipeline.context_manager.get_context(message.from_user.id)
    
    try:
        response = await _chat_service.chat(
            message.text,
            context=context,
            use_cloud=False,
        )
        
        await message.answer(response)
        return response
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        response = "Извините, сейчас не могу ответить. Попробуйте позже."
        await message.answer(response)
        return response


async def _handle_unknown(message: Message, result: NLUResult) -> str:
    """Обработка неизвестного намерения."""
    # Пробуем обработать как чат
    if result.intent.confidence < 0.5:
        return await _handle_chat(message, result)
    
    response = (
        "🤔 Не совсем понял запрос. Попробуйте:\n"
        "• «Найди статьи про machine learning»\n"
        "• «Покажи мою библиотеку»\n"
        "• «Сделай резюме первой статьи»\n"
        "• /help для списка команд"
    )
    await message.answer(response)
    return response
