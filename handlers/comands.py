from aiogram import Bot, Dispatcher, types  
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from services import ArxivSearcher, format_paper_message
from aiogram.utils.markdown import hbold, hitalic, hlink
import asyncio
from utils import setup_logger, InputValidator
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

logger = setup_logger(
    name="command_logger",
    level="INFO"
)
validator = InputValidator()

def register_command_handlers(dp: Dispatcher):

    dp.message.register(start_command, Command("start"))
    dp.message.register(help_command, Command("help"))
    dp.message.register(search_command, Command("search"))

async def start_command(message: Message):
    await message.answer("Здравствуйте! Используйте /help, чтобы увидеть доступные команды.")

async def help_command(message: Message):
    help_text = """

            🤖 **Доступные команды:**

        /start - Запустить бота
        /help - Показать это сообщение справки
        /search <запрос> - Поиск научных статей в ArXiv

        **Пример использования:**
        /search machine learning
        /search quantum computing
        /search neural networks
    """
    await message.answer(help_text, parse_mode="Markdown")

async def search_command(message: Message):
    
    query = message.text.replace("/search ", "").strip()
    query = validator.sanitize_text(query)
    if validator.contains_suspicious_content(query):
        await message.answer(
            "⚠️ Сообщение содержит потенциально небезопасный контент. "
            "Пожалуйста, будьте осторожны."
        )
        return
    
    if not query or query.strip() == "/search":
        await message.answer("Пожалуйста, введите запрос для поиска.")
        return
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    status_message = await message.answer(f"🔍 Ищу статьи по запросу: {query}...")
    
    try:
        async with ArxivSearcher() as searcher:
            papers = await searcher.search_papers(query)
            await status_message.delete()
        
        if not papers:
            await message.answer(
                f"😔 По запросу {hbold(query)} ничего не найдено.\n\n"
                f"💡 Попробуйте:\n"
                f"• Изменить ключевые слова\n"
                f"• Использовать английские термины\n"
                f"• Сделать запрос более общим"
            )
            return
        
        header = f"📚 Найдено {len(papers)} статей по запросу: {hbold(query)}\n\n"
        await message.answer(header)
        
        for i, paper in enumerate(papers, start=1):
            paper_message = format_paper_message(paper, i)
            
            keyboard = InlineKeyboardBuilder()
            keyboard.add(
                InlineKeyboardButton(
                    text="Ссылка на статью",
                    url=paper['link']
                )
            )
            
            await message.answer(
                paper_message,
                reply_markup=keyboard.as_markup(), 
                disable_web_page_preview=True
            )
            
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"Ошибка при выполнении команды /search: {e}")
        try:
            await status_message.delete()
        except:
            pass
        await message.answer(
            "❌ Произошла ошибка при поиске статей.\n"
            "🔄 Попробуйте еще раз через несколько секунд.\n\n"
            "🔧 Возможные причины:\n"
            "• Временная недоступность ArXiv API\n"
            "• Проблемы с интернет-соединением\n"
            "• Превышение лимита запросов"
        )