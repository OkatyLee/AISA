from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sympy import public
from config import COMMAND_MESSAGES, SEARCH_DELAY_SECONDS, TYPING_DELAY_SECONDS
import asyncio
from services.utils.keyboard import create_paper_keyboard
from utils.logger import setup_logger
from database import SQLDatabase as db
from aiogram.utils.markdown import hbold, hitalic, hlink
from services.utils.paper import Paper
import json
import hashlib

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
    async def _get_user_saved_urls(user_id: int) -> set:
        """Получение URL сохраненных пользователем статей"""
        try:
            user_library = await db.get_user_library(user_id, limit=1000)
            return {paper['url'] for paper in user_library}
        except Exception as e:
            logger.error(f"Ошибка при получении библиотеки пользователя {user_id}: {e}")
            return set()

    @staticmethod
    async def _get_user_saved_index(user_id: int) -> dict:
        """Возвращает индекс сохранённых статей: urls и пары (source, external_id)."""
        try:
            user_library = await db.get_user_library(user_id, limit=2000)
            urls = set()
            ids = set()
            title_hashes = set()
            for p in user_library:
                url = p.get('url')
                if url:
                    urls.add(url)
                src = (p.get('source') or '').lower()
                eid = (p.get('external_id') or '').strip()
                if src and eid:
                    ids.add((src, eid))
                title = p.get('title') or ''
                if title:
                    try:
                        import hashlib as _hash
                        title_hashes.add(_hash.sha256(title.encode()).hexdigest())
                    except Exception:
                        pass
            return {'urls': urls, 'ids': ids, 'title_hashes': title_hashes}
        except Exception as e:
            logger.error(f"Ошибка при построении индекса сохранённых статей {user_id}: {e}")
            return {'urls': set(), 'ids': set(), 'title_hashes': set()}

    @staticmethod
    async def _send_search_results(message: Message, papers: list, query: str, saved_urls: set):
        """Отправка результатов поиска с пагинацией"""
        if not papers:
            await SearchUtils._send_no_results_message(message, query)
            return
            
        # Сохраняем результаты поиска для пагинации
        search_id = SearchUtils._save_search_results(message.from_user.id, papers, query, saved_urls)
        
        # Отправляем первую страницу
        await SearchUtils._send_paginated_results(message, search_id, 0)
    
    @staticmethod
    def _save_search_results(user_id: int, papers: list, query: str, saved_urls: set) -> str:
        """Сохраняет результаты поиска во временном хранилище"""
        # Создаем уникальный ID для результатов поиска
        search_data = f"{user_id}_{query}_{len(papers)}"
        search_id = hashlib.md5(search_data.encode()).hexdigest()[:8]
        
        # Сохраняем в глобальное временное хранилище (в реальном проекте лучше использовать Redis)
        if not hasattr(SearchUtils, '_search_cache'):
            SearchUtils._search_cache = {}
            
        # Создаём расширенный индекс сохранённых
        # Примечание: saved_urls передаётся для обратной совместимости
        SearchUtils._search_cache[search_id] = {
            'papers': papers,
            'query': query,
            'saved_urls': saved_urls,
            'saved_index': None,  # будет заполнен при первом рендере
            'user_id': user_id
        }
        
        return search_id
    
    @staticmethod
    async def _send_paginated_results(message_or_callback, search_id: str, page: int = 0, edit_message: bool = False, auto_answer: bool = True):
        """Отправляет результаты поиска с пагинацией"""
        if not hasattr(SearchUtils, '_search_cache') or search_id not in SearchUtils._search_cache:
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.answer("❌ Результаты поиска устарели. Выполните поиск заново.")
            return
            
        search_data = SearchUtils._search_cache[search_id]
        papers = search_data['papers']
        query = search_data['query']
        # Всегда обновляем список сохранённых статей из БД, чтобы состояние кнопок было актуальным
        try:
            fresh_index = await SearchUtils._get_user_saved_index(search_data['user_id'])
            search_data['saved_urls'] = fresh_index['urls']
            search_data['saved_index'] = fresh_index
        except Exception as e:
            logger.debug(f"Не удалось обновить saved_urls из БД: {e}")
        saved_urls = search_data['saved_urls']
        saved_index = search_data.get('saved_index')
        
        papers_per_page = 1
        total_pages = len(papers)
        
        if page >= total_pages or page < 0:
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.answer("❌ Страница не найдена")
            return
            
        current_paper = papers[page]
        
        # Форматируем сообщение (используем HTML разметку корректно)
        header = f"📚 Результат {page + 1} из {total_pages} по запросу: <b>{query}</b>\n\n"
        paper_message = SearchUtils.format_paper_message(current_paper, page + 1)
        # format_paper_message возвращает HTML (hbold = <b>, hitalic = <i>, hlink = <a>)
        full_message = header + paper_message

        # Если редактируем и текст идентичен предыдущему – добавим zero-width space, чтобы избежать ошибки Telegram
        old_text = None
        if isinstance(message_or_callback, CallbackQuery) and edit_message:
            old_text = message_or_callback.message.text or ""
            if old_text == full_message:
                full_message += "\u200b"  # невидимый символ
        
        # Создаем клавиатуру с кнопками навигации и действий
        keyboard = SearchUtils._create_pagination_keyboard(
            search_id, page, total_pages, current_paper, search_data['user_id'], saved_urls, saved_index
        )
        
        try:
            if isinstance(message_or_callback, CallbackQuery) and edit_message:
                try:
                    await message_or_callback.message.edit_text(
                        full_message,
                        parse_mode="HTML",
                        reply_markup=keyboard.as_markup(),
                        disable_web_page_preview=True
                    )
                except TelegramBadRequest as te:
                    if "message is not modified" in str(te).lower():
                        # Попробуем просто обновить разметку (вдруг изменилась клавиатура)
                        try:
                            await message_or_callback.message.edit_reply_markup(
                                reply_markup=keyboard.as_markup()
                            )
                        except TelegramBadRequest:
                            pass  # Нечего обновлять
                    else:
                        raise
                if auto_answer:
                    await message_or_callback.answer()
            else:
                message = message_or_callback if isinstance(message_or_callback, Message) else message_or_callback.message
                await message.answer(
                    full_message,
                    parse_mode="HTML",
                    reply_markup=keyboard.as_markup(),
                    disable_web_page_preview=True
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке пагинированных результатов: {e}")
    
    @staticmethod
    def _create_pagination_keyboard(search_id: str, page: int, total_pages: int, paper: Paper, user_id: int, saved_urls: set, saved_index: dict | None = None) -> InlineKeyboardBuilder:
        """Создает клавиатуру для пагинации с кнопками действий"""
        keyboard = InlineKeyboardBuilder()
        
        # Кнопка ссылки на статью
        if paper.url:
            keyboard.add(InlineKeyboardButton(
                text="🔗 Читать статью",
                url=paper.url
            ))
        
        # Кнопки навигации
        nav_buttons = []
        
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"search_page:{search_id}:{page-1}"
            ))
        
        # Кнопка с текущей позицией
        nav_buttons.append(InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="current_page"
        ))
        
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(
                text="Вперед ▶️",
                callback_data=f"search_page:{search_id}:{page+1}"
            ))
        
        # Добавляем кнопки навигации в ряд
        for button in nav_buttons:
            keyboard.add(button)
        
        # Кнопки действий для статьи
        # Определяем сохранённость по URL или паре (source, external_id)
        is_saved = False
        if paper.url and paper.url in saved_urls:
            is_saved = True
        elif saved_index:
            src = (paper.source or '').lower()
            eid = (paper.external_id or '').strip()
            if src and eid and (src, eid) in saved_index.get('ids', set()):
                is_saved = True
        
        if is_saved:
            keyboard.add(InlineKeyboardButton(
                text="❌ Удалить из библиотеки",
                callback_data=paper.get_safe_callback_data("delete_paper")
            ))
        else:
            keyboard.add(InlineKeyboardButton(
                text="💾 Сохранить в библиотеку",
                callback_data=paper.get_safe_callback_data("save_paper")
            ))
        
        keyboard.add(InlineKeyboardButton(
            text="📊 Суммаризация",
            callback_data=paper.get_safe_callback_data("summary")
        ))
        
        # Кнопка закрытия результатов
        keyboard.add(InlineKeyboardButton(
            text="📋 Показать списком",
            callback_data=f"show_list:{search_id}"
        ))
        
        keyboard.add(InlineKeyboardButton(
            text="❌ Закрыть результаты",
            callback_data=f"close_search:{search_id}"
        ))
        
        # Настраиваем расположение кнопок
        if len(nav_buttons) == 1:
            keyboard.adjust(1, 1, 2, 2)  # ссылка, навигация, действия, управление
        elif len(nav_buttons) == 2:
            keyboard.adjust(1, 2, 2, 2)  # ссылка, навигация, действия, управление
        else:
            keyboard.adjust(1, 3, 2, 2)  # ссылка, навигация, действия, управление
        
        return keyboard
    
    @staticmethod
    def cleanup_old_searches():
        """Очистка старых результатов поиска для экономии памяти"""
        if not hasattr(SearchUtils, '_search_cache'):
            return
            
        # В реальном проекте лучше использовать TTL в Redis
        # Здесь просто ограничиваем количество сохраненных поисков
        if len(SearchUtils._search_cache) > 100:
            # Удаляем половину самых старых записей
            items = list(SearchUtils._search_cache.items())
            for key, _ in items[:len(items)//2]:
                del SearchUtils._search_cache[key]
    
    @staticmethod
    async def _send_search_results_as_list(message_or_callback, search_id: str):
        """Отправляет результаты поиска списком (старый формат)"""
        if not hasattr(SearchUtils, '_search_cache') or search_id not in SearchUtils._search_cache:
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.answer("❌ Результаты поиска устарели")
            return
            
        search_data = SearchUtils._search_cache[search_id]
        papers = search_data['papers']
        query = search_data['query']
        saved_urls = search_data['saved_urls']
        user_id = search_data['user_id']
        
        # Формируем сообщение со списком всех результатов
        header = f"📚 Найдено {len(papers)} статей по запросу: *{query}*\n\n"
        
        results_text = header
        for i, paper in enumerate(papers[:5], 1):  # Показываем только первые 5
            title = paper.title[:100] + "..." if len(paper.title) > 100 else paper.title
            authors = ", ".join(paper.authors[:2])
            if len(paper.authors) > 2:
                authors += f" и ещё {len(paper.authors) - 2}"
            
            results_text += f"{i}. **{title}**\n"
            results_text += f"   👥 {authors}\n"
            if paper.url:
                results_text += f"   🔗 [Читать статью]({paper.url})\n"
            results_text += "\n"
        
        if len(papers) > 5:
            results_text += f"... и ещё {len(papers) - 5} статей\n\n"
            results_text += "💡 Используйте пагинацию для просмотра всех результатов"
        
        # Создаем клавиатуру для возврата к пагинации
        keyboard = InlineKeyboardBuilder()
        keyboard.add(InlineKeyboardButton(
            text="📖 Вернуться к пагинации",
            callback_data=f"search_page:{search_id}:0"
        ))
        keyboard.add(InlineKeyboardButton(
            text="❌ Закрыть результаты",
            callback_data=f"close_search:{search_id}"
        ))
        
        try:
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.message.edit_text(
                    results_text,
                    parse_mode="Markdown",
                    reply_markup=keyboard.as_markup(),
                    disable_web_page_preview=True
                )
                await message_or_callback.answer()
            else:
                await message_or_callback.answer(
                    results_text,
                    parse_mode="Markdown",
                    reply_markup=keyboard.as_markup(),
                    disable_web_page_preview=True
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке результатов списком: {e}")
            
    @staticmethod        
    def format_paper_message(paper: Paper, index: int) -> str:
        """Форматирование информации о статье для вывода"""
        title = hbold(f"{index}. {paper.title}")
        
        authors_text = ', '.join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors_text += f" и еще {len(paper.authors) - 3} автора"
        authors = hitalic(authors_text)
        from datetime import datetime
        pub_date = paper.publication_date.date().isoformat() if isinstance(paper.publication_date, datetime) else paper.publication_date
        date = f'Опубликовано: {pub_date}' if pub_date else 'Дата публикации не указана'
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
