from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
import re
from typing import Dict, Any, Optional
from services.search.semantic_scholar_service import SemanticScholarSearcher
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
    def search_patterns(field: str, patterns: list[str], cleaned_query: str) -> Optional[str]:
        for pattern in patterns:
            match = re.search(pattern, cleaned_query, re.IGNORECASE)
            if match:
                filters[field] = match.group(1).strip()
                cleaned_query = re.sub(pattern, '', cleaned_query, flags=re.IGNORECASE)
        return cleaned_query
    
    # Извлечение фильтра по году
    year_patterns = [
        r'year:(>[0-9]{4})', # включает '>' + год
        r'year:(<[0-9]{4})', # включает '<' + год
        r'year:([0-9]{4})',
        r'year:"([0-9]{4})"',
        r"year:'([0-9]{4})'"
    ]


    cleaned_query = search_patterns('year', year_patterns, cleaned_query)

    # Извлечение фильтра по автору
    author_patterns = [
        r'author:"([^"]+)"',  # author:"John Smith"
        r"author:'([^']+)'",  # author:'John Smith'
        r'author:([^\s:]+)',    # author:smith
        r'au:"([^"]+)"',  # author:"John Smith"
        r"au:'([^']+)'",  # author:'John Smith'
        r'au:([^\s:]+)',    # author:smith
    ]
    cleaned_query = search_patterns('author', author_patterns, cleaned_query)

    # Извлечение фильтра по журналу
    journal_patterns = [
        r'journal:"([^"]+)"',
        r"journal:'([^']+)'",
        r'journal:([^\s:]+)',
        r'jr:"([^"]+)"',
        r"jr:'([^']+)'",
        r'jr:([^\s:]+)',
    ]
    cleaned_query = search_patterns('journal', journal_patterns, cleaned_query)

    # Извлечение фильтра по ключевым словам
    citation_count_patterns = [
        r'citation_count:>(\d+)',  # citation_count:>100
        r'citation_count:<(\d+)',  # citation_count:<100
        r'citation_count:(\d+)',  # citation_count:100
        r'citation_count:"(\d+)"',  # citation_count:"100"
        r'citation_count:\'(\d+)\'',  # citation_count:'100'
        r'citation:>(\d+)',  # citation_count:>100
        r'citation:<(\d+)',  # citation_count:<100
        r'citation:(\d+)',  # citation_count:100
        r'citation:"(\d+)"',  # citation_count:"100"
        r'citation:\'(\d+)\'',  # citation_count:'100'
        
    ]
    cleaned_query = search_patterns('citation_count', citation_count_patterns, cleaned_query)

    # Очищаем запрос от лишних пробелов
    cleaned_query = ' '.join(cleaned_query.split())
    
    logger.info(f"Извлеченные фильтры: {filters}, очищенный запрос: {cleaned_query}")

    cleaned_query = cleaned_query.replace('--arxiv', '-a')
    cleaned_query = cleaned_query.replace('--ieee', '-i')
    cleaned_query = cleaned_query.replace('--ncbi', '-n')
    cleaned_query = cleaned_query.replace('--semantic_scholar', '-s')
    cleaned_query = cleaned_query.replace('--count', '-c')
    sources_patterns = [
        '-a', '-i', '-n', '-s'
    ]
    filters['source'] = []
    for source in sources_patterns:
        source_mapping = {
            '-a': 'arxiv',
            '-n': 'ncbi',
            '-i': '-ieee',
            '-s': 'semantic_scholar'
        }
        if source in cleaned_query:
            filters['source'].append(source_mapping.get(source))
            cleaned_query = cleaned_query.replace(source, '').strip()
    if not filters['source']:
        filters['source'] = None
    if '-c' in cleaned_query:
        filters['count'] = int(re.search(r'-c\s*(\d+)', cleaned_query).group(1))
        if filters['count'] < 1:
            filters['count'] = 1
        cleaned_query = cleaned_query.replace(f'-c {filters["count"]}', '').strip()

    return cleaned_query, filters

def register_search_handlers(dp: Dispatcher):
    dp.message.register(arxiv_command, Command("arxiv"))
    dp.message.register(ieee_command, Command("ieee"))
    dp.message.register(ncbi_command, Command("ncbi"))
    dp.message.register(search_command, Command("search"))
    dp.message.register(semantic_search_command, Command("semantic_search"))


async def perform_search(
    message: Message,
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    source: Optional[str] = None,
) -> bool:
    """
    Универсальная функция поиска статей.
    
    Используется как командами (/search, /arxiv и т.д.), 
    так и NLU-обработчиком (chat_handler).
    
    Args:
        message: Telegram Message для ответа
        query: Поисковый запрос
        filters: Фильтры (year, author, journal и т.д.)
        source: Конкретный источник (arxiv, ieee, ncbi, semantic_scholar)
        
    Returns:
        bool: True если поиск успешен, False при ошибке
    """
    filters = filters or {}
    
    # Валидация запроса
    query = validator.sanitize_text(query)
    
    if not query or len(query) < 2:
        await SearchUtils._send_search_help(message)
        return False
    
    # Проверка на подозрительный контент
    if validator.contains_suspicious_content(query):
        await message.answer(
            "⚠️ Пожалуйста, используйте только научные термины для поиска."
        )
        return False
    
    # Показываем процесс поиска
    await message.bot.send_chat_action(message.chat.id, "typing")
    status_message = await message.answer(
        f"🔍 Ищу статьи по запросу: *{validator.escape_markdown(query)}*...",
        parse_mode="Markdown"
    )
    
    try:
        limits = filters.get('count', 100)
        
        # Выбираем сервис поиска
        if source:
            # Поиск в конкретном источнике
            source_lower = source.lower()
            if source_lower == 'arxiv':
                async with ArxivSearcher() as searcher:
                    papers = await searcher.search_papers(query, limit=limits, filters=filters)
            elif source_lower == 'ieee':
                async with IEEESearcher() as searcher:
                    papers = await searcher.search_papers(query, limit=limits, filters=filters)
            elif source_lower == 'ncbi' or source_lower == 'pubmed':
                async with NCBISearcher() as searcher:
                    papers = await searcher.search_papers(query, limit=limits, filters=filters)
            elif source_lower == 'semantic_scholar':
                async with SemanticScholarSearcher() as searcher:
                    papers = await searcher.search_papers(query, limit=limits, filters=filters)
            else:
                # Неизвестный источник — используем общий поиск
                async with SearchService() as search_service:
                    papers = await search_service.search_papers(query, limit=limits, filters=filters)
                    papers = search_service.aggregate_results(papers, query)
        else:
            # Универсальный поиск по всем источникам
            active_adapters = filters.get('source', None)
            async with SearchService() as search_service:
                papers = await search_service.search_papers(
                    query, limit=limits, services=active_adapters, filters=filters
                )
                papers = search_service.aggregate_results(papers, query)
        
        await status_message.delete()
        
        if not papers:
            await SearchUtils._send_no_results_message(message, query)
            return True  # Поиск успешен, просто нет результатов
        
        # Получаем сохраненные статьи пользователя для проверки
        saved_urls = await SearchUtils._get_user_saved_urls(message.from_user.id)
        
        # Отправляем результаты
        await SearchUtils._send_search_results(message, papers, query, saved_urls)
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при поиске: {e}")
        await ErrorHandler.handle_search_error(message, e, status_message)
        return False


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
    if (not query or query.strip() == "/search") and filters.get('author') is None:
        await SearchUtils._send_search_help(message)
        return

    if len(query) < 3 and filters.get('author') is None:
        await ErrorHandler.handle_validation_error(
            message,
            "Запрос слишком короткий. Пожалуйста, введите минимум 3 символа."
        )
        return
    
    # Показываем процесс поиска
    await asyncio.sleep(TYPING_DELAY_SECONDS)
    await message.bot.send_chat_action(message.chat.id, "typing")
    status_message = await message.answer(f"🔍 Ищу статьи по запросу: *{validator.escape_markdown(query)}*...", parse_mode="Markdown")
    limits = filters.get('count', 100)
    try:
        # Выполняем поиск
        async with ArxivSearcher() as searcher:
            papers = await searcher.search_papers(query, limit=limits, filters=filters)

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
        limits = filters.get('count', 100)
        async with IEEESearcher() as ieee_service:
            papers = await ieee_service.search_papers(query, limit=limits, filters=filters)

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
        limits = filters.get('count', 100)
        async with NCBISearcher() as ncbi_service:
            papers = await ncbi_service.search_papers(query, limit=limits, filters=filters)

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
        limits = filters.get('count', 100)
        active_adapters = filters.get('source', None)
        async with SearchService() as search_service:
            results = await search_service.search_papers(query, limit=limits, services=active_adapters, filters=filters)

        await status_message.delete()
        
        if not results:
            await SearchUtils._send_no_results_message(message, query)
            return
        
        # Получаем сохраненные статьи пользователя для проверки
        saved_urls = await SearchUtils._get_user_saved_urls(message.from_user.id)
        results = search_service.aggregate_results(results, query)
                # Отправляем результаты
        await SearchUtils._send_search_results(message, results, query, saved_urls)

    except Exception as e:
        await ErrorHandler.handle_search_error(message, e, status_message)
        
@track_operation("semantic_search_command")
async def semantic_search_command(message: Message, **kwargs):
    """
    Команда /semantic_search - поиск по семантическому контенту
    """
    query = message.text.replace("/semantic_search ", "").strip()
    if not query:
        await SearchUtils._send_search_help(message)
        return

    await message.bot.send_chat_action(message.chat.id, "typing")
    query, filters = extract_search_filters(query)
    query = validator.sanitize_text(query)
    status_message = await message.answer(f"🔍 Ищу статьи по семантическому запросу: *{validator.escape_markdown(query)}*...", parse_mode="Markdown")
    
    
    limits = filters.get('count', 100)
    if not query or len(query) < 3:
        await SearchUtils._send_search_help(message)
        return
    try:
        async with SemanticScholarSearcher() as search_service:
            results = await search_service.search_papers(query, limit=limits, filters=filters)

        await status_message.delete()

        if not results:
            await SearchUtils._send_no_results_message(message, query)
            return

        # Получаем сохраненные статьи пользователя для проверки
        saved_urls = await SearchUtils._get_user_saved_urls(message.from_user.id)
        # Отправляем результаты
        await SearchUtils._send_search_results(message, results, query, saved_urls)

    except Exception as e:
        logger.error(f"Ошибка при поиске статей: {e}")
        await ErrorHandler.handle_search_error(message, e, status_message)
