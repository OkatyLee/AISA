from aiogram.types import Message
from config import COMMAND_MESSAGES, SEARCH_DELAY_SECONDS, TYPING_DELAY_SECONDS
import asyncio
from utils.keyboard import create_paper_keyboard
from utils.logger import setup_logger
from database import SQLDatabase as db
from aiogram.utils.markdown import hbold, hitalic, hlink
from services.utils.paper import Paper

logger = setup_logger(
    name="search_commands_logger",
    level="INFO"
)

class SearchUtils:

    @staticmethod
    async def _send_search_help(message: Message):
        """Отправка справки по команде поиска"""
        await message.bot.send_chat_action(message.chat.id, "typing")
        await asyncio.sleep(TYPING_DELAY_SECONDS)
        search_help_text = COMMAND_MESSAGES['search_help']
        await message.answer(search_help_text, parse_mode="Markdown")
        
    @staticmethod
    async def _send_no_results_message(message: Message, query: str):
        """Сообщение об отсутствии результатов поиска"""
        await message.answer(
            f"😔 По запросу *{query}* ничего не найдено.\n\n"
            f"💡 **Попробуйте:**\n"
            f"• Изменить ключевые слова\n"
            f"• Использовать английские термины\n"
            f"• Сделать запрос более общим\n"
            f"• Проверить правописание",
            parse_mode="Markdown"
        )
    @staticmethod
    async def _send_search_help(message: Message):
        """Отправка справки по команде поиска"""
        await message.bot.send_chat_action(message.chat.id, "typing")
        await asyncio.sleep(TYPING_DELAY_SECONDS)
        search_help_text = COMMAND_MESSAGES['search_help']
        await message.answer(search_help_text, parse_mode="Markdown")
    @staticmethod
    async def _send_no_results_message(message: Message, query: str):
        """Сообщение об отсутствии результатов поиска"""
        await message.answer(
                f"😔 По запросу *{query}* ничего не найдено.\n\n"
                f"💡 **Попробуйте:**\n"
                f"• Изменить ключевые слова\n"
                f"• Использовать английские термины\n"
                f"• Сделать запрос более общим\n"
                f"• Проверить правописание",
                parse_mode="Markdown"
            )
    @staticmethod
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
        header = f"📚 Найдено *{str(len(papers))}* статей по запросу: *{query}*\n"
        await message.answer(header, parse_mode="Markdown")
        
        for i, paper in enumerate(papers, start=1):
            try:
                paper_message = SearchUtils.format_paper_message(paper, i)
                is_saved = paper in saved_urls
                keyboard = create_paper_keyboard(paper, message.from_user.id, is_saved) 
                await message.answer(
                    paper_message,
                    parse_mode="HTML",
                    reply_markup=keyboard.as_markup(), 
                    disable_web_page_preview=True
                )
                
                await asyncio.sleep(SEARCH_DELAY_SECONDS)
                
            except Exception as e:
                logger.error(f"Ошибка при отправке статьи {i}: {e}")
                continue
            
    @staticmethod        
    def format_paper_message(paper: Paper, index: int) -> str:
        """Форматирование информации о статье для вывода"""
        title = hbold(f"{index}. {paper.title}")
        
        authors_text = ', '.join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_text += f" и еще {len(paper.authors) - 3} автора"
        authors = hitalic(authors_text)

        date = f'Опубликовано: {paper.publication_date}' if paper.publication_date else 'Дата публикации не указана'
        keywords = ''
        if paper.keywords:
            keywords = ', '.join(paper.keywords[:3])

        summary = f"📄 {paper.abstract[:200]}..."

        # Ссылка
        url = hlink("🔗 Читать статью", paper.url)
        
        # Собираем всё вместе
        parts = [title, authors, date]
        if keywords:
            parts.append(keywords)
        parts.extend([summary, url])
        return '\n'.join(parts)
