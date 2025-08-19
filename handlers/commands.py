from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
import asyncio
from services.search.semantic_scholar_service import SemanticScholarSearcher
from services.utils.paper import Paper
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
    dp.message.register(recommendations_command, Command("recommendations"))
    dp.message.register(app_features_command, Command("features"))
    dp.message.register(app_demo_command, Command("demo"))


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
    Команда /library - просмотр сохраненных статей через расширенное Mini App
    """
    try:
        config = load_config()
        
        # URL Mini App (в production должен быть HTTPS)
        webapp_url = config.WEBAPP_URL
        
        # Создаем клавиатуру с кнопкой Mini App
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="� Научный ассистент", 
                web_app=WebAppInfo(url=webapp_url)
            )],
            [InlineKeyboardButton(
                text="📊 Статистика", 
                callback_data="library_stats"
            )]
        ])
        
        # Получаем краткую статистику
        user_id = message.from_user.id
        library = await db.get_library_status(user_id)
        
        if not library:
            msg = (
                f"� **Добро пожаловать в расширенное Mini App!**\n\n"
                f"🆕 **Новые возможности:**\n"
                f"� Управление библиотекой\n"
                f"🔍 Продвинутый поиск статей\n"
                f"🎯 Персональные рекомендации\n"
                f"� AI-ассистент с NLP\n"
                f"🏷️ Интеллектуальные теги\n\n"
                f"Ваша библиотека пока пуста. Используйте поиск или чат для нахождения статей!\n\n"
                f"👇 Откройте приложение:"
            )
        else:
            msg = (
                f"🚀 **Научный ассистент** - теперь с расширенными возможностями!\n\n"
                f"📚 **Ваша библиотека: {library['total_papers']} статей**\n\n"
                f"🆕 **Новые функции в Mini App:**\n"
                f"🔍 **Умный поиск** - по всем научным базам\n"
                f"🎯 **Рекомендации** - персональные предложения\n"
                f"💬 **AI-чат** - понимает естественный язык\n"
                f"� **Аналитика** - статистика по тегам и авторам\n"
                f"🏷️ **Теги** - организация и фильтрация\n\n"
            )

            if library.get('popular_tags'):
                msg += "📂 **Популярные теги:**\n"
                for tag, count in library['popular_tags'][:3]:
                    msg += f"• {tag}: {count} статей\n"
                msg += "\n"
        
            if library.get('popular_authors'):
                msg += "👨‍🔬 **Популярные авторы:**\n"
                for author, count in library['popular_authors'][:3]:
                    msg += f"• {author}: {count} статей\n"
                msg += "\n"

            msg += "👇 Откройте расширенный ассистент:"
        
        await message.answer(
            msg,
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

@track_operation("recommendations_command")
async def recommendations_command(message: Message, **kwargs):
    """Команда /recommendations - показать похожие статьи"""
    user_id = message.from_user.id

    query = message.text.replace('/recommendations', '').strip()

    if not query:
        await message.answer(
            "🔍 Готовлю рекомендации на основе вашей библиотеки..."
        )
        
        papers = await db.get_user_library(user_id)
        papers = [Paper(**paper) for paper in papers]
        if not papers:
            await message.answer("📚 **Ваша библиотека пуста**", parse_mode="Markdown")
            return

        # Формируем и отправляем сообщения с похожими статьями
        async with SemanticScholarSearcher() as s2_ss:
            recommendations = await s2_ss.get_recommendations_for_multiple_papers(papers, 100)

        if not recommendations:
            await message.answer(
                "❌ Не удалось найти похожие статьи. Попробуйте позже."
            )
            return

        saved_urls = await SearchUtils._get_user_saved_urls(user_id)
        
        await SearchUtils._send_search_results(message, recommendations, 'recommendations', saved_urls)
    else:
        urls = query.split(' ')
        if len(urls) > 1:
            try:
                async with SemanticScholarSearcher() as s2_ss:
                    papers = [Paper(url=url) for url in urls]
                    recommendations = await s2_ss.get_recommendations_for_multiple_papers(papers, 100)
        
                if not recommendations:
                    await message.answer(
                        "❌ Не удалось найти похожие статьи. Проверьте список ваших URLs."
                    )
                    return

                saved_urls = await SearchUtils._get_user_saved_urls(user_id)
                    
                await SearchUtils._send_search_results(message, recommendations, 'recommendations', saved_urls)

            except Exception as e:
                logger.error(f"Ошибка при получении рекомендаций: {e}")
                await message.answer("❌ Не удалось получить рекомендации. Попробуйте позже. Возможно ваши URLs слишком длинные.")
                return
        else:
            async with SemanticScholarSearcher() as s2_ss:
                id = s2_ss._extract_paper_id_from_url(urls[0])
                recommendations = await s2_ss.get_recommendation_for_single_paper(id, 30)
        
            if not recommendations:
                await message.answer(
                    "❌ Не удалось найти похожие статьи. Проверьте ваш URL."
                )
                return

            saved_urls = await SearchUtils._get_user_saved_urls(user_id)
                
            await SearchUtils._send_search_results(message, recommendations, 'recommendations', saved_urls)


@track_operation("app_features_command")
async def app_features_command(message: Message, **kwargs):
    """Команда /features - показать новые возможности Mini App"""
    features_text = (
        "🚀 **Новые возможности Научного ассистента**\n\n"
        
        "🔍 **Умный поиск статей:**\n"
        "• Поиск по всем научным базам (ArXiv, IEEE, PubMed, Semantic Scholar)\n"
        "• Продвинутые фильтры (автор, год, источник)\n"
        "• Автоматическое определение лучших источников\n\n"
        
        "💬 **AI-Чат ассистент:**\n"
        "• Понимает естественный язык\n"
        "• Обработка контекстных запросов\n"
        "• Интеллектуальные рекомендации\n"
        "• Помощь в формулировке запросов\n\n"
        
        "🎯 **Персональные рекомендации:**\n"
        "• На основе вашей библиотеки\n"
        "• Семантический анализ интересов\n"
        "• Актуальные статьи в вашей области\n\n"
        
        "📚 **Расширенная библиотека:**\n"
        "• Интеллектуальные теги\n"
        "• Гибкая фильтрация и сортировка\n"
        "• Статистика и аналитика\n"
        "• Быстрый поиск по содержимому\n\n"
        
        "🏷️ **Управление тегами:**\n"
        "• Автоматическая категоризация\n"
        "• Редактирование тегов\n"
        "• Группировка по тематикам\n\n"
        
        "**Попробуйте команду /demo для интерактивной демонстрации!**"
    )
    
    await message.answer(features_text, parse_mode="Markdown")

@track_operation("app_demo_command") 
async def app_demo_command(message: Message, **kwargs):
    """Команда /demo - интерактивная демонстрация"""
    config = load_config()
    webapp_url = config.WEBAPP_URL
    
    demo_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🚀 Открыть Demo Mini App", 
            web_app=WebAppInfo(url=webapp_url)
        )],
        [InlineKeyboardButton(text="🔍 Попробовать поиск", callback_data="demo_search"),
         InlineKeyboardButton(text="💬 Тест чат", callback_data="demo_chat")],
        [InlineKeyboardButton(text="🎯 Рекомендации", callback_data="demo_recommendations"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="demo_stats")]
    ])
    
    demo_text = (
        "🎮 **Интерактивная демонстрация**\n\n"
        "Выберите что хотите попробовать:\n\n"
        "🚀 **Mini App** - полнофункциональное приложение\n"
        "🔍 **Поиск** - найти статьи прямо сейчас\n" 
        "💬 **Чат** - пообщаться с AI-ассистентом\n"
        "🎯 **Рекомендации** - получить предложения\n"
        "📊 **Статистика** - посмотреть аналитику\n\n"
        "**Или просто напишите что вас интересует!**"
    )
    
    await message.answer(
        demo_text,
        reply_markup=demo_keyboard,
        parse_mode="Markdown"
    )

