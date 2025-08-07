from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
import re
from typing import Dict, Any, Optional
from utils.metrics import track_operation
from services.search import ArxivSearcher, IEEESearcher, NCBISearcher
from services.search import SearchService
from utils.validators import InputValidator
from utils.error_handler import ErrorHandler
from utils.logger import setup_logger
import asyncio
from services.utils import SearchUtils

from config import TYPING_DELAY_SECONDS

logger = setup_logger(
    name="search_commands_logger",
    level="INFO"
)

validator = InputValidator()


def extract_search_filters(query: str) -> tuple[str, Dict[str, Any]]:
    """
    Извлекает фильтры из поискового запроса.
    
    Поддерживаемые фильтры:
    - year:2023 или year:"2023"
    - author:"John Smith" или author:smith
    
    Returns:
        tuple: (cleaned_query, filters_dict)
    """
    filters = {}
    cleaned_query = query
    
    # Извлечение фильтра по году
    year_patterns = [
        r'year:(\d{4})',  # year:2023
        r'year:"(\d{4})"',  # year:"2023"
        r'year:\'(\d{4})\''  # year:'2023'
    ]
    
    for pattern in year_patterns:
        match = re.search(pattern, cleaned_query, re.IGNORECASE)
        if match:
            filters['year'] = int(match.group(1))
            cleaned_query = re.sub(pattern, '', cleaned_query, flags=re.IGNORECASE)
            break
    
    # Извлечение фильтра по автору
    author_patterns = [
        r'author:"([^"]+)"',  # author:"John Smith"
        r"author:'([^']+)'",  # author:'John Smith'
        r'author:([^\s]+)'    # author:smith
    ]
    
    for pattern in author_patterns:
        match = re.search(pattern, cleaned_query, re.IGNORECASE)
        if match:
            filters['author'] = match.group(1).strip()
            cleaned_query = re.sub(pattern, '', cleaned_query, flags=re.IGNORECASE)
            break
    
    # Очищаем запрос от лишних пробелов
    cleaned_query = ' '.join(cleaned_query.split())
    
    return cleaned_query, filters

def register_search_handlers(dp: Dispatcher):
    dp.message.register(arxiv_command, Command("arxiv"))
    dp.message.register(ieee_command, Command("ieee"))
    dp.message.register(ncbi_command, Command("ncbi"))
    dp.message.register(search_command, Command("search"))


@track_operation("arxiv_command")
async def arxiv_command(message: Message, **kwargs):
    """
    Команда /arxiv - поиск научных статей
    
    Включает валидацию, индикацию процесса и обработку ошибок
    """
    # Извлечение и валидация запроса
    query = message.text.replace("/arxiv ", "").strip()
    
    # Извлекаем фильтры из запроса
    query, filters = extract_search_filters(query)
    
    query = validator.sanitize_text(query)
    
    # Проверка на потенциально опасный контент
    if validator.contains_suspicious_content(query):
        await ErrorHandler.handle_validation_error(
            message, 
            "Пожалуйста, используйте только научные термины для поиска."
        )
        return
    
    # Валидация запроса
    if not query or query.strip() == "/search":
        await SearchUtils._send_search_help(message)
        return
    
    if len(query) < 3:
        await ErrorHandler.handle_validation_error(
            message,
            "Запрос слишком короткий. Пожалуйста, введите минимум 3 символа."
        )
        return
    
    # Показываем процесс поиска
    await asyncio.sleep(TYPING_DELAY_SECONDS)
    await message.bot.send_chat_action(message.chat.id, "typing")
    status_message = await message.answer(f"🔍 Ищу статьи по запросу: *{validator.escape_markdown(query)}*...", parse_mode="Markdown")

    try:
        # Выполняем поиск
        async with ArxivSearcher() as searcher:
            papers = await searcher.search_papers(query, 10, filters)
            
        await status_message.delete()
        
        if not papers:
            await SearchUtils._send_no_results_message(message, query)
            return
        
        # Получаем сохраненные статьи пользователя для проверки
        saved_urls = await SearchUtils._get_user_saved_urls(message.from_user.id)

        # Отправляем результаты
        await SearchUtils._send_search_results(message, papers, query, saved_urls)

    except Exception as e:
        await ErrorHandler.handle_search_error(message, e, status_message)
        
@track_operation("ieee_command")        
async def ieee_command(message: Message, **kwargs):
    """
    Команда /ieee - поиск статей в IEEE Xplore
    """
    try:
        query = message.text.replace("/ieee ", "").strip()
        
        # Извлекаем фильтры из запроса
        query, filters = extract_search_filters(query)
        
        query = validator.sanitize_text(query)
        
        if not query or len(query) < 3:
            await message.answer("❌ Пожалуйста, введите корректный запрос (минимум 3 символа).")
            return
        
        await message.bot.send_chat_action(message.chat.id, "typing")
        status_message = await message.answer(f"🔍 Ищу статьи в IEEE по запросу: *{query}*...", parse_mode="Markdown")
        
        async with IEEESearcher() as ieee_service:
            papers = await ieee_service.search_papers(query, 10, filters)
        
        await status_message.delete()
        
        if not papers:
            await SearchUtils._send_no_results_message(message, query)
            return
        
        # Получаем сохраненные статьи пользователя для проверки
        saved_urls = await SearchUtils._get_user_saved_urls(message.from_user.id)

        # Отправляем результаты
        await SearchUtils._send_search_results(message, papers, query, saved_urls)
    
    except Exception as e:
        logger.error(f"Ошибка при поиске статей в IEEE: {e}")
        await ErrorHandler.handle_search_error(message, e)
        
@track_operation("ncbi_command")
async def ncbi_command(message: Message, **kwargs):
    """
    Команда /ncbi - поиск статей в NCBI
    """
    try:
        query = message.text.replace("/ncbi ", "").strip()
        
        # Извлекаем фильтры из запроса
        query, filters = extract_search_filters(query)
        
        query = validator.sanitize_text(query)

        if not query or len(query) < 3:
            await message.answer("❌ Пожалуйста, введите корректный запрос (минимум 3 символа).")
            return

        await message.bot.send_chat_action(message.chat.id, "typing")
        status_message = await message.answer(f"🔍 Ищу статьи в NCBI по запросу: *{query}*...", parse_mode="Markdown")

        async with NCBISearcher() as ncbi_service:
            papers = await ncbi_service.search_papers(query, 10, filters)

        await status_message.delete()

        if not papers:
            await SearchUtils._send_no_results_message(message, query)
            return

        # Получаем сохраненные статьи пользователя для проверки
        saved_urls = await SearchUtils._get_user_saved_urls(message.from_user.id)

        # Отправляем результаты
        await SearchUtils._send_search_results(message, papers, query, saved_urls)

    except Exception as e:
        logger.error(f"Ошибка при поиске статей в NCBI: {e}")
        await ErrorHandler.handle_search_error(message, e)
        
@track_operation("search_command")
async def search_command(message: Message, **kwargs):
    """
    Команда /search - универсальный поиск по всем сервисам
    """
    query = message.text.replace("/search ", "").strip()
    params_keywords = ['-a', '-i', '-n', '-c']
    params = {}
    if any(keyword in query for keyword in params_keywords):
        for keyword in params_keywords:
            if keyword in query:
                value = query.split(keyword)[-1].strip().split(" ")[0]
                params[keyword] = value
                query = query.replace(keyword + " " + value, "").strip()
    if not query:
        await SearchUtils._send_search_help(message)
        return
    
    # Извлекаем фильтры из запроса
    query, filters = extract_search_filters(query)
    
    query = validator.sanitize_text(query)
    if not query or len(query) < 3:
        await SearchUtils._send_search_help(message)
        return
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    status_message = await message.answer(f"🔍 Ищу статьи по запросу: *{validator.escape_markdown(query)}*...", parse_mode="Markdown")
    
    try:
        limit = params.get('-c', 5)
        active_adapters = []
        if any(keyword in query for keyword in ['--arxiv', '-a']):
            active_adapters.append('arxiv')
        if any(keyword in query for keyword in ['--ieee', '-i']):
            active_adapters.append('ieee')
        if any(keyword in query for keyword in ['--ncbi', '-n']):
            active_adapters.append('ncbi')
        if not active_adapters:
            active_adapters = None
        search_service = SearchService()
        results = await search_service.search_papers(query, limit=limit, services=active_adapters, filters=filters)
        
        await status_message.delete()
        
        if not results:
            await SearchUtils._send_no_results_message(message, query)
            return
        
        # Получаем сохраненные статьи пользователя для проверки
        saved_urls = await SearchUtils._get_user_saved_urls(message.from_user.id)
        results = search_service.aggregate_results(results)
        # Отправляем результаты
        await SearchUtils._send_search_results(message, results, query, saved_urls)

    except Exception as e:
        logger.error(f"Ошибка при поиске статей: {e}")
        await ErrorHandler.handle_search_error(message, e, status_message)