from database import SQLDatabase as db
from services.search import SearchService
from services.utils.paper import Paper
from services.nlp import LLMService
from services.utils.keyboard import create_paper_keyboard 
from utils.error_handler import ErrorHandler
from utils.metrics import track_operation
from aiogram.types import CallbackQuery
from aiogram import types
from aiogram import Dispatcher
from utils import setup_logger
import logging

logger = setup_logger(
    name="library_logger",
    level=logging.DEBUG
)


def register_library_handlers(dp: Dispatcher):
    dp.callback_query.register(
        handle_save_paper,
        lambda c: c.data.startswith("save_paper:")
    )
    
    dp.callback_query.register(
        handle_library_delete,
        lambda c: c.data.startswith("delete_paper:")
    )
    
    dp.callback_query.register(
        handle_library_stats,
        lambda c: c.data == "library_stats"
    )
    
    dp.callback_query.register(
        handle_export_bibtex,
        lambda c: c.data == "export_bibtex"
    )
    
    dp.callback_query.register(
        handle_summary,
        lambda c: c.data.startswith("summary:")
    )

@track_operation("save_paper")
async def handle_save_paper(callback: CallbackQuery, **kwargs):
    """Обработчик сохранения статьи в библиотеку пользователя"""
    try:
        # Парсим callback данные: save_paper:source:id или save_paper:url:id или save_paper:hash:id
        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат данных")
            return
            
        callback_type = parts[1]  # source, url, hash
        callback_value = parts[2]  # actual id/value
        
        user_id = callback.from_user.id
        print("пытаемся найти статью")
        # Получаем статью, заново запрашивая ее по ID
        paper = None
        async with SearchService() as searcher:
            paper = await searcher.get_paper_by_identifier(callback_type, callback_value, user_id)
        print("нашли статью")
        if not paper:
            await callback.answer("❌ Не удалось найти данные статьи для сохранения.")
            return
        paper_dict = paper.to_dict() if isinstance(paper, Paper) else paper
        print('заходим в save_paper')
        success = await db.save_paper(user_id, paper_dict)
        print('выход из save_paper')
        if success:
            await callback.message.edit_reply_markup(
                reply_markup=create_paper_keyboard(
                    paper, user_id, is_saved=True
                ).as_markup()
            )
            await callback.answer("✅ Статья сохранена в библиотеку!")
        else:
            await callback.answer("❌ Статья уже сохранена в библиотеке")
            
    except Exception as e:
        logger.error(f"Ошибка при сохранении статьи: {e}")
        await callback.answer("❌ Ошибка при сохранении статьи")


@track_operation("library_stats")
async def handle_library_stats(callback: CallbackQuery, **kwargs):
    """Обработчик показа статистики библиотеки"""
    try:
        user_id = callback.from_user.id
        library = await db.get_user_library(user_id)
        
        if not library:
            await callback.answer("📚 Ваша библиотека пуста")
            return
        
        # Подсчитываем статистику
        total_papers = len(library)
        categories = {}
        recent_papers = 0
        
        from datetime import datetime, timedelta
        month_ago = datetime.now() - timedelta(days=30)
        
        for paper in library:
            # Категории
            if paper.get("categories"):
                for cat in paper["categories"]:
                    cat = cat.strip()
                    categories[cat] = categories.get(cat, 0) + 1
            
            # Недавние статьи
            if paper.get("saved_at"):
                try:
                    saved_date = datetime.fromisoformat(paper["saved_at"].replace("Z", "+00:00"))
                    if saved_date >= month_ago:
                        recent_papers += 1
                except:
                    pass
        
        # Формируем сообщение
        stats_message = f"📊 **Статистика библиотеки**\n\n"
        stats_message += f"📚 Всего статей: {total_papers}\n"
        stats_message += f"🆕 За последний месяц: {recent_papers}\n\n"
        
        if categories:
            stats_message += "📂 **Популярные категории:**\n"
            sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
            for cat, count in sorted_cats:
                stats_message += f"• {cat}: {count} статей\n"
        else:
            stats_message += "📂 Категории не найдены\n"
        
        await callback.message.answer(stats_message, parse_mode="Markdown")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики библиотеки: {e}")
        await callback.answer("❌ Ошибка при получении статистики")


@track_operation("library_delete")  
async def handle_library_delete(callback: CallbackQuery, **kwargs):
    """Обработчик удаления статьи из библиотеки"""
    try:
        # Парсим callback данные: delete_paper:source:id или delete_paper:url:id или delete_paper:hash:id
        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат данных")
            return
            
        callback_type = parts[1]  # source, url, hash
        callback_value = parts[2]  # actual id/value
        
        user_id = callback.from_user.id
        
        # Удаляем статью из библиотеки по callback данным
        # В зависимости от типа callback данных используем разные методы поиска
        success = False
        
        if callback_type in ['arxiv', 'pubmed', 'ieee', 'doi']:
            # Поиск по внешнему ID и источнику
            success = await db.delete_paper_by_external_id(user_id, callback_value, callback_type)
        elif callback_type == 'url':
            # Поиск по части URL
            success = await db.delete_paper_by_url_part(user_id, callback_value)
        elif callback_type == 'hash':
            # Поиск по хешу заголовка
            success = await db.delete_paper_by_title_hash(user_id, callback_value)
        
        if success:
            await callback.answer("✅ Статья удалена из библиотеки")
            # Обновляем сообщение, убираем кнопки
            await callback.message.edit_text(
                callback.message.text + "\n\n❌ Статья удалена из библиотеки",
                parse_mode="Markdown"
            )
        else:
            await callback.answer("❌ Ошибка при удалении статьи")
            
    except Exception as e:
        logger.error(f"Ошибка при удалении статьи из библиотеки: {e}")
        await callback.answer("❌ Ошибка при удалении статьи")


@track_operation("export_bibtex")
async def handle_export_bibtex(callback: CallbackQuery, **kwargs):
    """Обработчик экспорта библиотеки в BibTeX"""
    try:
        user_id = callback.from_user.id
        bibtex_content = await db.export_library_bibtex(user_id)
        
        if bibtex_content:
            with open(f"library_{user_id}.bib", "w", encoding="utf-8") as f:
                f.write(bibtex_content)
            
            with open(f"library_{user_id}.bib", "rb") as f:
                await callback.message.answer_document(
                    document=types.BufferedInputFile(
                        f.read(),
                        filename=f"library_{user_id}.bib"
                    ),
                    caption="📁 Ваша библиотека в формате BibTeX"
                )
            
            await callback.answer("✅ Файл отправлен!")
        else:
            await callback.answer("❌ Библиотека пуста")
            
    except Exception as e:
        logger.error(f"Ошибка при экспорте библиотеки: {e}")
        await callback.answer("❌ Ошибка при экспорте")

    
@track_operation("summary")        
async def handle_summary(callback: CallbackQuery, **kwargs):
    """Обработчик суммаризации статьи"""
    try:
        user_id = callback.from_user.id
        
        # Парсим callback данные: summary:source:id или summary:url:id или summary:hash:id
        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат данных")
            return
            
        callback_type = parts[1]  # source, url, hash
        callback_value = parts[2]  # actual id/value
        
        await callback.answer("Начинаю суммаризацию...")

        # Получаем статью в зависимости от типа callback данных
        paper = None
        logger.debug(f"Получение статьи по {callback_type} с ID {callback_value} для пользователя {user_id}")
        async with SearchService() as searcher:
            paper = await searcher.get_paper_by_identifier(callback_type, callback_value, user_id)

        if paper:
            processing_msg = await callback.message.answer(
                "⏳ Суммаризирую статью, это может занять некоторое время..."
            )
            async with LLMService() as llm_service:
                summary = await llm_service.summarize(paper)
                
            if processing_msg:
                await processing_msg.delete()
            await callback.message.answer(summary, parse_mode="Markdown")
            
        else:
            await callback.message.answer("❌ Статья не найдена")
            
    except Exception as e:
        logger.error(f"Ошибка при суммаризации статьи: {e}")
        await ErrorHandler.handle_summarization_error(callback, e)