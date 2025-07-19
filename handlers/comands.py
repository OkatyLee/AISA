from email.mime import text
from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from services import ArxivSearcher, format_paper_message
from aiogram.utils.markdown import hbold
import asyncio
from utils import setup_logger, InputValidator
from utils import create_library_keyboard, create_paper_keyboard
from utils.error_handler import ErrorHandler
from utils.metrics import track_operation, metrics
from database import SQLDatabase as db
from typing import Optional

# Импорты констант и сообщений
from config.constants import (
    MAX_MESSAGE_LENGTH, 
    SEARCH_DELAY_SECONDS, 
    TYPING_DELAY_SECONDS
)
from config.messages import (
    ERROR_MESSAGES, 
    SUCCESS_MESSAGES, 
    INFO_MESSAGES,
    COMMAND_MESSAGES,
    EMOJI
)

logger = setup_logger(
    name="command_logger",
    level="INFO"
)
validator = InputValidator()
SEARCH_DELAY_SECONDS = 0.3  # Задержка между сообщениями
TYPING_DELAY_SECONDS = 0.5  # Задержка перед показом typing



def register_command_handlers(dp: Dispatcher):

    dp.message.register(start_command, Command("start"))
    dp.message.register(help_command, Command("help"))
    dp.message.register(search_command, Command("search"))
    dp.message.register(library_command, Command("library"))
    dp.message.register(stats_command, Command("stats")) 

@track_operation("start_command")
async def start_command(message: Message, **kwargs):
    """Команда /start - приветствие пользователя"""
    await message.answer(COMMAND_MESSAGES['start_welcome'], parse_mode="Markdown")

@track_operation("help_command")
async def help_command(message: Message, **kwargs):
    """Команда /help - справка по использованию бота"""
    await message.answer(COMMAND_MESSAGES['help_text'], parse_mode="Markdown")

@track_operation("search_command")
async def search_command(message: Message, **kwargs):
    """
    Команда /search - поиск научных статей
    
    Включает валидацию, индикацию процесса и обработку ошибок
    """
    # Извлечение и валидация запроса
    query = message.text.replace("/search ", "").strip()
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
        await _send_search_help(message)
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
    status_message = await message.answer(f"🔍 Ищу статьи по запросу: *{query}*...", parse_mode="Markdown")
    
    try:
        # Выполняем поиск
        async with ArxivSearcher() as searcher:
            papers = await searcher.search_papers(query)
            
        await status_message.delete()
        
        if not papers:
            await _send_no_results_message(message, query)
            return
        
        # Получаем сохраненные статьи пользователя для проверки
        saved_urls = await _get_user_saved_urls(message.from_user.id)
        
        # Отправляем результаты
        await _send_search_results(message, papers, query, saved_urls)

    except Exception as e:
        await ErrorHandler.handle_search_error(message, e, status_message)

async def _send_search_help(message: Message):
    """Отправка справки по команде поиска"""
    await message.answer(COMMAND_MESSAGES['search_help'], parse_mode="Markdown")

async def _send_no_results_message(message: Message, query: str):
    """Сообщение об отсутствии результатов поиска"""
    await message.answer(
        f"😔 По запросу {hbold(query)} ничего не найдено.\n\n"
        f"💡 **Попробуйте:**\n"
        f"• Изменить ключевые слова\n"
        f"• Использовать английские термины\n"
        f"• Сделать запрос более общим\n"
        f"• Проверить правописание"
    )

async def _get_user_saved_urls(user_id: int) -> set:
    """Получение URL сохраненных пользователем статей"""
    try:
        user_library = await db.get_user_library(user_id, limit=1000)
        return {paper['url'] for paper in user_library}
    except Exception as e:
        logger.error(f"Ошибка при получении библиотеки пользователя {user_id}: {e}")
        return set()

async def _send_search_results(message: Message, papers: list, query: str, saved_urls: set):
    """Отправка результатов поиска"""
    header = f"📚 Найдено {hbold(str(len(papers)))} статей по запросу: {hbold(query)}\n"
    await message.answer(header)
    
    for i, paper in enumerate(papers, start=1):
        try:
            paper_message = format_paper_message(paper, i)
            is_saved = paper['url'] in saved_urls
            keyboard = create_paper_keyboard(paper, message.from_user.id, is_saved)
            
            await message.answer(
                paper_message,
                reply_markup=keyboard.as_markup(), 
                disable_web_page_preview=True
            )
            
            await asyncio.sleep(SEARCH_DELAY_SECONDS)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке статьи {i}: {e}")
            continue

async def library_command(message: Message):
    """
    Команда /library - просмотр сохраненных статей
    
    Включает пагинацию и улучшенное форматирование
    """
    try:
        user_id = message.from_user.id
        library = await db.get_user_library(user_id)
        
        if not library:
            await _send_empty_library_message(message)
            return
            
        await _send_library_contents(message, library, user_id)
    
    except Exception as e:
        await ErrorHandler.handle_library_error(message, e)

async def _send_empty_library_message(message: Message):
    """Сообщение о пустой библиотеке"""
    await message.answer(
        "📚 **Ваша библиотека пуста**\n\n"
        "🔍 Используйте команду `/search <запрос>` для поиска статей\n"
        "💾 Сохраняйте интересные статьи нажатием кнопки \"💾 Сохранить\"\n\n"
        "**Пример:** `/search machine learning`",
        parse_mode="Markdown"
    )

async def _send_library_contents(message: Message, library: list, user_id: int):
    """Отправка содержимого библиотеки"""
    total_count = len(library)
    header = (
        f"📚 **Ваша библиотека** ({hbold(str(total_count))} "
        f"{'статья' if total_count == 1 else 'статей' if total_count < 5 else 'статей'})\n"
    )
    await message.answer(header)
    
    for i, paper in enumerate(library, start=1):
        try:
            paper_message = format_paper_message(paper, i)
            keyboard = create_library_keyboard(paper, user_id, is_saved=True)
            
            await message.answer(
                paper_message,
                reply_markup=keyboard.as_markup(),
                disable_web_page_preview=True
            )
            
            await asyncio.sleep(SEARCH_DELAY_SECONDS)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке статьи из библиотеки {i}: {e}")
            continue

@track_operation("stats_command")
async def stats_command(message: Message, **kwargs):
    """Команда /stats - статистика работы бота (только для админов)"""
    user_id = message.from_user.id
    
    if user_id != : 
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    try:
        # Получаем статистику за последние 24 часа
        stats_24h = metrics.get_stats(24)
        
        # Получаем статистику за последний час
        stats_1h = metrics.get_stats(1)
        
        # Формируем сообщение
        stats_message = (
            f"📊 **Статистика работы бота**\n\n"
            f"**📈 За последние 24 часа:**\n"
            f"• Всего операций: {stats_24h['total_operations']}\n"
            f"• Активных пользователей: {stats_24h['active_users']}\n"
            f"• Поиск статей: {stats_24h['operation_counts'].get('search_command', 0)}\n"
            f"• Просмотр библиотеки: {stats_24h['operation_counts'].get('library_command', 0)}\n\n"
            
            f"**⏱ За последний час:**\n"
            f"• Всего операций: {stats_1h['total_operations']}\n"
            f"• Активных пользователей: {stats_1h['active_users']}\n\n"
            
            f"**🔍 ArXiv API:**\n"
            f"• Успешные поиски: {stats_24h['operation_counts'].get('arxiv_search_success', 0)}\n"
            f"• Попадания в кэш: {stats_24h['operation_counts'].get('arxiv_search_cache_hit', 0)}\n"
            f"• Ошибки: {stats_24h['operation_counts'].get('arxiv_search_http_error', 0) + stats_24h['operation_counts'].get('arxiv_search_timeout', 0)}\n\n"
        )
        
        # Добавляем времена выполнения если есть
        if stats_24h['average_timings']:
            stats_message += "**⏱️ Средние времена выполнения:**\n"
            for operation, avg_time in stats_24h['average_timings'].items():
                if 'search' in operation:
                    stats_message += f"• {operation}: {avg_time:.2f}с\n"
            stats_message += "\n"
        
        await message.answer(stats_message, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await ErrorHandler.handle_stats_error(message, e)