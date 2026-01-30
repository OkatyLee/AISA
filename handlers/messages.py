"""
DEPRECATED: Этот модуль устарел и будет удален в следующей версии.
Используйте handlers.chat_handler вместо этого.

Для обновления импортов:
    OLD: from handlers.messages import MessageHandler
    NEW: from handlers.chat_handler import handle_message
"""

import warnings
warnings.warn(
    "handlers.messages is deprecated. Use handlers.chat_handler instead.",
    DeprecationWarning,
    stacklevel=2
)

import os
from aiogram import Dispatcher, F
from aiogram.types import Message, FSInputFile
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
logger = setup_logger(
    name='messages_logger',
    level='DEBUG'
)

# Backward-compatible shim for tests expecting class-based handler
class MessageHandler:
    def __init__(self, *args, **kwargs):
        # args are ignored; modern flow uses nlp.query_processor internally
        pass

    async def handle(self, text: str) -> str:
        # Minimal shim: mimic processing a generic message without Telegram context
        # This is for test suite compatibility only.
        fake = type("_Msg", (), {})()
        fake.text = text
        fake.from_user = type("_U", (), {"id": 0})()
        fake.chat = type("_C", (), {"id": 0})()

        # Provide minimal answer method to collect response
        responses = []
        async def _answer(t, **kwargs):
            responses.append(str(t))
        async def _answer_document(doc, **kwargs):
            # record that a document would be sent
            responses.append(f"<document:{getattr(doc, 'path', 'file')}>")
        fake.answer = _answer
        fake.answer_document = _answer_document

        # Route into existing pipeline with a default intent path
        try:
            result = await query_processor.process(text, {})
            await _handle_processed_query(fake, result)
        except Exception as _:
            # fallback generic message
            responses.append("Не удалось обработать сообщение")
        # Return last response text for tests
        return responses[-1] if responses else ""

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
    logger.debug(f"Обработка намерения поиска с параметрами: {params}")
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
    Поддерживает: URL, DOI, arXiv ID, PubMed ID, IEEE ID или свободный текст с ссылкой/ID.
    """
    try:
        from services.search import SearchService
        from services.nlp import LLMService
        from services.utils.paper import Paper
        from nlp.entity_classifier import RuleBasedEntityExtractor
        from utils.nlu.intents import Intent as _Intent
        from services.utils.search_utils import SearchUtils
        from utils.report import save_md_and_pdf, delete_report_files

        user_id = message.from_user.id
        identifier = None
        id_type = None
        raw_text = params.get("query") or ""
        text_lower = raw_text.lower()
        compare_request = any(x in text_lower for x in [
            "сравн", "compare", "несколько", "оба", "две", "двух", "3 статьи", "неск стат", "сравни"
        ])

        # Приоритет: явные поля в params
        for key in ["url", "doi", "arxiv_id", "pubmed_id", "ieee_id"]:
            if key in params and params[key]:
                identifier = params[key]
                id_type = key
                break

        # Попытка извлечь несколько идентификаторов из текста
        identifiers: list[tuple[str, str]] = []
        if raw_text:
            extractor = RuleBasedEntityExtractor()
            extracted = await extractor.extract(raw_text, _Intent.GET_SUMMARY)
            for e in extracted.entities:
                if e.type.value in ["url", "doi", "arxiv_id", "pubmed_id", "ieee_id"]:
                    identifiers.append((e.type.value, str(e.normalized_value or e.value)))
        logger.debug(f"Извлеченные идентификаторы до дедупликации: {identifiers}")
        # Дедупликация
        if identifiers:
            seen = set()
            uniq = []
            for t, v in identifiers:
                k = (t, v)
                if k not in seen:
                    seen.add(k)
                    uniq.append((t, v))
            identifiers = uniq
        logger.debug(f"Извлеченные идентификаторы: {identifiers}")
        # Мульти-анализ, если просили сравнение и нашли >=2 id
        if compare_request and len(identifiers) >= 2:
            async with SearchService() as searcher:
                processing_msg = await message.answer("🔍 Ищу статьи для сравнения...")
                type_map = {
                    "url": "url",
                    "doi": "doi",
                    "arxiv_id": "arxiv",
                    "pubmed_id": "pubmed",
                    "ieee_id": "ieee",
                }
                papers: list[Paper] = []
                for t, v in identifiers[:5]:
                    cb_type = type_map.get(t, "url")
                    try:
                        p = await searcher.get_paper_by_identifier(cb_type, v, user_id)
                        if isinstance(p, Paper):
                            papers.append(p)
                    except Exception:
                        continue
                if not papers:
                    await message.answer("❌ Не удалось найти статьи для сравнения")
                    return "Не удалось найти статьи для сравнения"
                try:
                    items = await searcher.fetch_full_texts_for_papers(papers)
                    if processing_msg:
                        await processing_msg.edit_text("⏳ Готовлю сравнительный анализ нескольких статей…")
                    else:
                        processing_msg = await message.answer("⏳ Готовлю сравнительный анализ нескольких статей…")
                    async with LLMService() as llm_service:
                        summary = await llm_service.compare_many(items)
                finally:
                    try:
                        await processing_msg.delete()
                    except Exception:
                        pass
                # Сохраняем и отправляем как документ: MD всегда, PDF при наличии
                base_name = "comparison_report"
                await processing_msg.edit_text("📄 Сохраняю результаты анализа в документ")
                if summary == "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже.":
                    await processing_msg.edit_text("❌ " + summary)
                    return "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже."
                md_path, pdf_path = save_md_and_pdf(summary, base_name)
                await processing_msg.delete()
                if pdf_path and os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
                    await message.answer_document(FSInputFile(pdf_path), caption="Сравнительный анализ (PDF)")
                else:
                    await message.answer_document(FSInputFile(md_path), caption="Сравнительный анализ (Markdown)")
                delete_report_files(base_name)
                return "Сравнительный анализ завершен"

        # Если нет явного идентификатора
        if not identifier:
            # Попробуем сравнение по последнему поиску
            if compare_request and not identifiers:
                sid, data = SearchUtils._get_last_active_search(user_id)
                papers = []
                if data and data.get('papers'):
                    papers = data['papers'][:3]
                if papers:
                    processing_msg = await message.answer("🔍 Ищу тексты статьей из последнего поиска для сравнения...")
                    async with SearchService() as searcher:
                        items = await searcher.fetch_full_texts_for_papers(papers)
                        async with LLMService() as llm_service:
                            await processing_msg.edit_text("⏳ Готовлю сравнительный анализ найденных статей…")
                            summary = await llm_service.compare_many(items)
                    
                    base_name = "comparison_report"
                    if summary == "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже.":
                        await processing_msg.edit_text("❌ " + summary)
                        return "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже."
                    md_path, pdf_path = save_md_and_pdf(summary, base_name)
                    logger.debug(f'MD: {md_path}, exists= {os.path.isfile(md_path)}, size= {os.path.getsize(md_path) if os.path.isfile(md_path) else 0}')
                    if pdf_path and os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
                        await message.answer_document(FSInputFile(pdf_path), caption="Сравнительный анализ (PDF)")
                    else:
                        await message.answer_document(FSInputFile(md_path), caption="Сравнительный анализ (Markdown)")
                    await processing_msg.delete()
                    delete_report_files(base_name)
                    return "Сравнительный анализ завершен"

            # Или используем текущую выбранную статью
            try:
                current_paper = SearchUtils.get_current_paper_for_user(user_id)
            except Exception:
                current_paper = None
            if current_paper:
                processing_msg = await message.answer("⏳ Анализирую текущую выбранную статью…")
                async with LLMService() as llm_service:
                    
                    summary = await llm_service.summarize(current_paper)
                    
                base_name = "article_analysis"
                if summary == "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже.":
                    await processing_msg.edit_text("❌ " + summary)
                    return "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже."
                md_path, pdf_path = save_md_and_pdf(summary, base_name)
                if pdf_path and os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
                    await message.answer_document(FSInputFile(pdf_path), caption="Анализ статьи (PDF)")
                else:
                    await message.answer_document(FSInputFile(md_path), caption="Анализ статьи (Markdown)")
                delete_report_files(base_name)
                return "Анализ завершен"

            # Просим указать идентификатор
            response = (
                "Чтобы сделать анализ, пришлите ссылку на статью или укажите её DOI/ID (arXiv, PubMed, IEEE)."
            )
            await message.answer(response)
            return response

        # Получаем статью по идентификатору (одна статья)
        async with SearchService() as searcher:
            type_map = {
                "url": "url",
                "doi": "doi",
                "arxiv_id": "arxiv",
                "pubmed_id": "pubmed",
                "ieee_id": "ieee",
            }
            processing_msg = await message.answer("🔍 Ищу полный текст статьи…")
            callback_type = type_map.get(id_type, "url")
            paper = await searcher.get_paper_by_identifier(callback_type, str(identifier), user_id, full_text=True)

        if not paper:
            response = "❌ Не удалось найти статью по указанной ссылке/ID."
            await message.answer(response)
            return response
        if processing_msg:
            await processing_msg.edit_text("⏳ Анализирую статью, это может занять некоторое время…")
        else:
            processing_msg = await message.answer("⏳ Анализирую статью, это может занять некоторое время…")
        async with LLMService() as llm_service:
            summary = await llm_service.summarize(paper)
        
        base_name = "article_analysis"
        if summary == "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже.":
            await processing_msg.edit_text("❌ " + summary)
            return "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже."
        md_path, pdf_path = save_md_and_pdf(summary, base_name)
        await processing_msg.edit_text("📄 Сохраняю результаты анализа в документ")
        logger.debug(f"MD: {md_path}, exists={os.path.isfile(md_path)}, size={os.path.getsize(md_path) if os.path.isfile(md_path) else 0}")
        logger.debug(f"PDF: {pdf_path}, exists={os.path.isfile(pdf_path) if pdf_path else False}, size={os.path.getsize(pdf_path) if pdf_path and os.path.isfile(pdf_path) else 0}")
        if processing_msg:
            try:
                await processing_msg.delete()
            except Exception:
                pass
        if pdf_path and os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
            await message.answer_document(FSInputFile(pdf_path), caption="Анализ статьи (PDF)")
        else:
            await message.answer_document(FSInputFile(md_path), caption="Анализ статьи (Markdown)")
        delete_report_files(base_name)
        return "Анализ завершен"
    except Exception as e:
        await ErrorHandler.handle_summarization_error(message, e)
        return "Произошла ошибка при анализе"

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