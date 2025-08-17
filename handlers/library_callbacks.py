from operator import call
from database import SQLDatabase as db
from services.search import SearchService
from services.search.semantic_scholar_service import SemanticScholarSearcher
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
import re
from services.utils.search_utils import SearchUtils
from utils.validators import InputValidator

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

    dp.callback_query.register(
        handle_recommendations,
        lambda c: c.data.startswith("recs:")
    )
    # Зарезервировано для будущей кнопки сравнения нескольких статей (compare:search_id:idx1,idx2,...)
    # dp.callback_query.register(handle_compare_many, lambda c: c.data.startswith("compare:"))

@track_operation("save_paper")
async def handle_save_paper(callback: CallbackQuery, **kwargs):
    """Обработчик сохранения статьи в библиотеку пользователя"""
    try:
        # Парсим callback данные: save_paper:source:id или save_paper:url:id или save_paper:hash:id
        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат данных")
            return

        callback_type = parts[1]
        callback_value = parts[2]
        user_id = callback.from_user.id
        logger.debug(f"{callback_type} {callback_value}")
        # Получаем статью, заново запрашивая ее по ID
        paper = None
        async with SearchService() as searcher:
            paper = await searcher.get_paper_by_identifier(callback_type, callback_value, user_id)
        if not paper:
            await callback.answer("❌ Не удалось найти данные статьи для сохранения.")
            return

        paper_dict = paper.to_dict() if isinstance(paper, Paper) else paper
        success = await db.save_paper(user_id, paper_dict)

        if not success:
            # Уже сохранена – всё равно обновим пагинацию, если это поиск, чтобы кнопка сменилась
            is_paginated_search = callback.message.text.startswith("📚 Результат") if callback.message.text else False
            if is_paginated_search:
                # Переиспользуем логику определения страницы / search_id из ниже, но минимально
                current_page_index = None
                search_id = None
                m = re.search(r"Результат (\d+) из (\d+)", callback.message.text)
                if m:
                    try:
                        current_page_index = int(m.group(1)) - 1
                    except ValueError:
                        current_page_index = None
                if callback.message.reply_markup:
                    try:
                        for row in callback.message.reply_markup.inline_keyboard:
                            for btn in row:
                                data = getattr(btn, 'callback_data', '') or ''
                                if data.startswith('search_page:'):
                                    parts_btn = data.split(':')
                                    if len(parts_btn) == 3:
                                        search_id = parts_btn[1]
                                        break
                                elif data.startswith('show_list:') and not search_id:
                                    parts_btn = data.split(':')
                                    if len(parts_btn) == 2:
                                        search_id = parts_btn[1]
                            if search_id:
                                break
                    except Exception:
                        pass
                if search_id and current_page_index is not None:
                    await SearchUtils._send_paginated_results(
                        callback, search_id, current_page_index, edit_message=True, auto_answer=False
                    )
                    await callback.answer("✅ Статья уже сохранена")
                    return
            await callback.answer("✅ Статья уже сохранена в библиотеке")
            return

        # Определяем, относится ли сообщение к пагинированным результатам поиска
        is_paginated_search = False
        current_page_index = None
        search_id = None

        message_text = callback.message.text or ""
        if message_text.startswith("📚 Результат"):
            # Пытаемся вытащить номер текущей страницы
            m = re.search(r"Результат (\d+) из (\d+)", message_text)
            if m:
                try:
                    current_page = int(m.group(1))
                    total_pages = int(m.group(2))  # noqa: F841 (может пригодиться позже)
                    current_page_index = current_page - 1
                    is_paginated_search = True
                except ValueError:
                    pass

        # Если навигация есть в reply_markup, извлекаем search_id
        if is_paginated_search and callback.message.reply_markup:
            try:
                for row in callback.message.reply_markup.inline_keyboard:
                    for btn in row:
                        data = getattr(btn, 'callback_data', '') or ''
                        if data.startswith('search_page:'):
                            # Формат: search_page:search_id:page
                            parts_btn = data.split(':')
                            if len(parts_btn) == 3:
                                search_id = parts_btn[1]
                                break
                        elif data.startswith('show_list:') and not search_id:
                            # Формат: show_list:search_id
                            parts_btn = data.split(':')
                            if len(parts_btn) == 2:
                                search_id = parts_btn[1]
                    if search_id:
                        break
            except Exception as ex:
                logger.debug(f"Не удалось извлечь search_id из клавиатуры: {ex}")

        # Если это пагинированный поиск и удалось определить search_id и страницу — перерисовываем через SearchUtils
        if is_paginated_search and search_id is not None and current_page_index is not None:
            # Обновляем кэш: добавляем url в saved_urls, чтобы кнопка сменилась на 'Удалить'
            if hasattr(SearchUtils, '_search_cache') and search_id in getattr(SearchUtils, '_search_cache'):
                try:
                    cache_entry = SearchUtils._search_cache[search_id]
                    if paper.url:
                        cache_entry['saved_urls'].add(paper.url)
                except Exception as ex:
                    logger.debug(f"Не удалось обновить saved_urls в кэше: {ex}")

            # Перерисовываем текущую страницу с обновленной клавиатурой
            await SearchUtils._send_paginated_results(
                callback, search_id, current_page_index, edit_message=True, auto_answer=False
            )
            await callback.answer("✅ Статья сохранена в библиотеку!")
            return

        # Иначе (не пагинация) — поведение по-старому: заменяем клавиатуру
        await callback.message.edit_reply_markup(
            reply_markup=create_paper_keyboard(
                paper, user_id, is_saved=True
            ).as_markup()
        )
        await callback.answer("✅ Статья сохранена в библиотеку!")

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
        success = False
        if callback_type in ['arxiv', 'pubmed', 'ieee', 'doi']:
            success = await db.delete_paper_by_external_id(user_id, callback_value, callback_type)
        elif callback_type == 'url':
            success = await db.delete_paper_by_url_part(user_id, callback_value)
        elif callback_type == 'hash':
            success = await db.delete_paper_by_title_hash(user_id, callback_value)

        if not success:
            await callback.answer("❌ Ошибка при удалении статьи")
            return

        # Определяем, относится ли сообщение к пагинированным результатам поиска
        is_paginated_search = False
        current_page_index = None
        search_id = None
        message_text = callback.message.text or ""
        if message_text.startswith("📚 Результат"):
            m = re.search(r"Результат (\d+) из (\d+)", message_text)
            if m:
                try:
                    current_page_index = int(m.group(1)) - 1
                    is_paginated_search = True
                except ValueError:
                    current_page_index = None

        if is_paginated_search and callback.message.reply_markup:
            try:
                for row in callback.message.reply_markup.inline_keyboard:
                    for btn in row:
                        data = getattr(btn, 'callback_data', '') or ''
                        if data.startswith('search_page:'):
                            parts_btn = data.split(':')
                            if len(parts_btn) == 3:
                                search_id = parts_btn[1]
                                break
                        elif data.startswith('show_list:') and not search_id:
                            parts_btn = data.split(':')
                            if len(parts_btn) == 2:
                                search_id = parts_btn[1]
                    if search_id:
                        break
            except Exception:
                pass

        if is_paginated_search and search_id is not None and current_page_index is not None:
            # Перерисовываем текущую страницу с обновленной клавиатурой (кнопка станет «Сохранить»)
            from services.utils.search_utils import SearchUtils as _SU
            await _SU._send_paginated_results(
                callback, search_id, current_page_index, edit_message=True, auto_answer=False
            )
            await callback.answer("✅ Статья удалена из библиотеки")
            return

        # Иначе (не пагинация): обновляем только клавиатуру, не удаляя кнопки
        try:
            paper = None
            async with SearchService() as searcher:
                paper = await searcher.get_paper_by_identifier(callback_type, callback_value, user_id)
            if paper:
                await callback.message.edit_reply_markup(
                    reply_markup=create_paper_keyboard(paper, user_id, is_saved=False).as_markup()
                )
            await callback.answer("✅ Статья удалена из библиотеки")
        except Exception:
            # В крайнем случае просто ответим, не ломая сообщение
            await callback.answer("✅ Статья удалена из библиотеки")

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
        
        await callback.answer("Начинаю анализ...")

        # Получаем статью в зависимости от типа callback данных
        paper = None
        logger.debug(f"Получение статьи по {callback_type} с ID {callback_value} для пользователя {user_id}")
        async with SearchService() as searcher:
            paper = await searcher.get_paper_by_identifier(callback_type, callback_value, user_id, full_text=True)
        if paper is None:
            await callback.message.answer("❌ Статья не найдена или не является openAccess")
        if paper:
            processing_msg = await callback.message.answer(
                "⏳ Анализирую статью, это может занять некоторое время..."
            )
            async with LLMService() as llm_service:
                summary = await llm_service.summarize(paper)
                
            if processing_msg:
                await processing_msg.delete()
            base_name = 'article_summary'
            if summary == "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже.":
                await processing_msg.edit_text("❌ " + summary)
                return "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже."
            from utils.report import save_md_and_pdf, delete_report_files
            md_name, pdf_name = save_md_and_pdf(summary, base_name)
            if pdf_name:
                await callback.message.answer_document(
                    types.FSInputFile(pdf_name), caption="Суммаризация статьи (PDF)"
                )
            else:
                await callback.message.answer_document(
                    types.FSInputFile(md_name), caption="Суммаризация статьи (Markdown)"
                )
            delete_report_files(base_name)
            await callback.message.answer(summary, parse_mode="Markdown")

        else:
            await callback.message.answer("❌ Статья не найдена")
            
    except Exception as e:
        logger.error(f"Ошибка при суммаризации статьи: {e}")
        await ErrorHandler.handle_summarization_error(callback, e)
        
@track_operation("handle_recommendations")
async def handle_recommendations(callback: CallbackQuery, **kwargs):
    """Обработчик показа похожих статей"""
    try:
        user_id = callback.from_user.id
        
        # Парсим callback данные: recommendation:source:id или recommendation:url:id или recommendation:hash:id
        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат данных")
            return
            
        callback_type = parts[1]  # source, url, hash
        callback_value = parts[2]  # actual id/value
        if callback_type == 'arxiv':
            callback_value = f"ARXIV:{callback_value}"
        elif callback_type == 'pubmed' or callback_type == 'ncbi':
            callback_value = f"PMID:{callback_value}"
        elif callback_type == 'ieee':
            callback_value = f"IEEE:{callback_value}"
        elif callback_type == 'doi':   
            callback_value = f"DOI:{callback_value}"
        elif callback_type == 'pmc':
            callback_value = f"PMC:{callback_value}"

        await callback.answer("🔍 Ищу похожие статьи...")
        
        async with SemanticScholarSearcher() as searcher:
            recommendations = await searcher.get_recommendation_for_single_paper(callback_value)
        
        if not recommendations:
            await callback.message.answer("❌ Похожие статьи не найдены. Попробуйте позже")
            return
        
        # Получаем сохраненные статьи пользователя для проверки
        saved_urls = await SearchUtils._get_user_saved_urls(callback.from_user.id)
        # Отправляем результаты
        await SearchUtils._send_search_results(callback.message, recommendations, 'recommendations', saved_urls)

    except Exception as e:
        logger.error(f"Ошибка при получении рекомендаций: {e}")
        await callback.answer("❌ Ошибка при получении рекомендаций")