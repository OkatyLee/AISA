from aiogram import Dispatcher
from aiogram.types import CallbackQuery
from services.utils.search_utils import SearchUtils
from utils.logger import setup_logger

logger = setup_logger(
    name="pagination_logger",
    level="INFO"
)

def register_pagination_handlers(dp: Dispatcher):
    """Регистрация обработчиков для пагинации результатов поиска"""
    dp.callback_query.register(
        handle_search_page,
        lambda c: c.data.startswith("search_page:")
    )
    
    dp.callback_query.register(
        handle_close_search,
        lambda c: c.data.startswith("close_search:")
    )
    
    dp.callback_query.register(
        handle_show_list,
        lambda c: c.data.startswith("show_list:")
    )
    
    dp.callback_query.register(
        handle_current_page,
        lambda c: c.data == "current_page"
    )

async def handle_search_page(callback: CallbackQuery):
    """Обработчик навигации по страницам результатов поиска"""
    try:
        # Периодически очищаем старые результаты поиска
        SearchUtils.cleanup_old_searches()
        
        # Парсим данные: search_page:search_id:page
        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("❌ Неверный формат данных")
            return
            
        search_id = parts[1]
        page = int(parts[2])
        
        # Отправляем запрошенную страницу
        await SearchUtils._send_paginated_results(callback, search_id, page, edit_message=True)
        
    except ValueError:
        await callback.answer("❌ Неверный номер страницы")
    except Exception as e:
        logger.error(f"Ошибка при навигации по результатам поиска: {e}")
        await callback.answer("❌ Ошибка при переходе на страницу")

async def handle_close_search(callback: CallbackQuery):
    """Обработчик закрытия результатов поиска"""
    try:
        # Парсим данные: close_search:search_id
        parts = callback.data.split(":")
        if len(parts) != 2:
            await callback.answer("❌ Неверный формат данных")
            return
            
        search_id = parts[1]
        
        # Удаляем сообщение
        await callback.message.delete()
        
        # Очищаем кэш для этого поиска
        if hasattr(SearchUtils, '_search_cache') and search_id in SearchUtils._search_cache:
            del SearchUtils._search_cache[search_id]
            
        await callback.answer("✅ Результаты поиска закрыты")
        
    except Exception as e:
        logger.error(f"Ошибка при закрытии результатов поиска: {e}")
        await callback.answer("❌ Ошибка при закрытии")

async def handle_current_page(callback: CallbackQuery):
    """Обработчик для кнопки текущей страницы (информационная)"""
    await callback.answer("ℹ️ Вы находитесь на текущей странице")

async def handle_show_list(callback: CallbackQuery):
    """Обработчик показа результатов поиска списком"""
    try:
        # Парсим данные: show_list:search_id
        parts = callback.data.split(":")
        if len(parts) != 2:
            await callback.answer("❌ Неверный формат данных")
            return
            
        search_id = parts[1]
        
        # Показываем результаты списком
        await SearchUtils._send_search_results_as_list(callback, search_id)
        
    except Exception as e:
        logger.error(f"Ошибка при показе результатов списком: {e}")
        await callback.answer("❌ Ошибка при отображении списка")
