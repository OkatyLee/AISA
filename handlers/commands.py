from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
import asyncio
from utils import setup_logger, InputValidator
from services.utils.keyboard import create_paper_keyboard
from utils.error_handler import ErrorHandler
from utils.metrics import track_operation, metrics
from database import SQLDatabase as db
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from config.config import load_config
from services.utils.search_utils import SearchUtils

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
ADMIN_IDS = load_config().ADMIN_IDS


def register_command_handlers(dp: Dispatcher):

    dp.message.register(start_command, Command("start"))
    dp.message.register(help_command, Command("help"))
    dp.message.register(library_command, Command("library"))
    dp.message.register(stats_command, Command("stats")) 
    dp.message.register(help_search_command, Command("help_search"))


@track_operation("start_command")
async def start_command(message: Message, **kwargs):
    """Команда /start - приветствие пользователя"""
    start_message = COMMAND_MESSAGES['start_welcome']
    await message.answer(start_message, parse_mode="Markdown")

@track_operation("help_command")
async def help_command(message: Message, **kwargs):
    """Команда /help - справка по использованию бота"""
    help_message = COMMAND_MESSAGES['help_text']
    await message.answer(help_message, parse_mode="Markdown")

@track_operation("library_command")
async def library_command(message: Message, **kwargs):
    """
    Команда /library - просмотр сохраненных статей через Mini App
    """
    try:
        config = load_config()
        
        # URL Mini App (в production должен быть HTTPS)
        webapp_url = config.WEBAPP_URL  # Замените на ваш URL
        
        # Создаем клавиатуру с кнопкой Mini App
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📚 Открыть библиотеку", 
                web_app=WebAppInfo(url=webapp_url)
            )],
            [InlineKeyboardButton(
                text="📊 Статистика", 
                callback_data="library_stats"
            )]
        ])
        
        # Получаем краткую статистику
        user_id = message.from_user.id
        library = await db.get_user_library(user_id)
        
        if not library:
            msg = f"📚 **Ваша библиотека пуста**\n\n" \
                f"🔍 Используйте команду `/search <запрос>` для поиска статей\n" \
                f"💾 Сохраняйте интересные статьи нажатием кнопки \"Сохранить\"\n\n" \
                f"👇 Или откройте библиотеку для удобного просмотра:"
            
            await message.answer(
                msg,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        # Подсчитываем категории
        categories = {}
        for paper in library:
            if paper.get("categories"):
                for cat in paper["categories"]:
                    cat = cat.strip()
                    categories[cat] = categories.get(cat, 0) + 1
        
        # Формируем сообщение со статистикой
        stats_text = f"📚 **Ваша библиотека: {len(library)} статей**\n\n"
        
        if categories:
            stats_text += "📂 **Популярные категории:**\n"
            sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
            for cat, count in sorted_cats:
                stats_text += f"• {cat}: {count} статей\n"
            stats_text += "\n"
        
        stats_text += "👇 Откройте библиотеку для удобного просмотра и управления статьями:"
        
        await message.answer(
            stats_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
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
        f"📚 **Ваша библиотека** (*{str(total_count)}* "
        f"{'статья' if total_count == 1 else 'статьи' if total_count < 5 else 'статей'})\n"
    )
    await message.answer(header, parse_mode="Markdown")

    for i, paper in enumerate(library, start=1):
        try:
            paper_message = SearchUtils.format_paper_message(paper, i)
            keyboard = create_paper_keyboard(paper, user_id, is_saved=True)
            await message.answer(
                paper_message,
                reply_markup=keyboard.as_markup(),
                disable_web_page_preview=True,
                parse_mode="Markdown"
            )
            
            await asyncio.sleep(SEARCH_DELAY_SECONDS)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке статьи из библиотеки {i}: {e}")
            continue

@track_operation("help_search_command")
async def help_search_command(message: Message, **kwargs):
    """Команда /help search - справка по поиску"""
    await message.answer(COMMAND_MESSAGES['search_help'], parse_mode="Markdown")

@track_operation("stats_command")
async def stats_command(message: Message, **kwargs):
    """Команда /stats - статистика работы бота (только для админов)"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS: 
        await message.answer("❌ У вас нет доступа к этой команде.", parse_mode="Markdown")
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
        

