from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def create_paper_keyboard(paper: dict, user_id: int, is_saved: bool = False) -> InlineKeyboardBuilder:
    """
    Создание клавиатуры для статьи
    
    Args:
        paper: Данные о статье
        user_id: ID пользователя
        is_saved: Сохранена ли статья пользователем
    """
    keyboard = InlineKeyboardBuilder()
    # Кнопка ссылки на статью
    keyboard.add(
        InlineKeyboardButton(
            text="🔗 Ссылка на статью",
            url=paper['url']
        )
    )
    
    # Кнопка сохранения/удаления
    if is_saved:
        keyboard.add(
            InlineKeyboardButton(
                text="❌ Удалить из библиотеки",
                callback_data=f"delete_paper:{paper['url']}"
            )
        )
    else:
        keyboard.add(
            InlineKeyboardButton(
                text="💾 Сохранить в библиотеку",
                callback_data=f"save_paper:{paper['url']}"
            )
        )
        
    if is_saved:
        keyboard.add(
            InlineKeyboardButton(
                text="🏷️ Добавить теги",
                callback_data=f"add_tags:{paper['url']}"
            )
        )
        
    keyboard.add(
        InlineKeyboardButton(
            text="📊 Суммаризация",
            callback_data=f"summary:{paper['url']}"
        )
    )
    
    summary_callback = f"summary:{paper['url']}"
    
    
    if is_saved:
        keyboard.adjust(1, 2, 1)
    else:
        keyboard.adjust(1, 1, 1)
    
    
    return keyboard

def create_library_keyboard(paper: dict, paper_id: int) -> InlineKeyboardBuilder:
    """
    Создание клавиатуры для статьи в библиотеке
    
    Args:
        paper: Данные о статье из библиотеки
        paper_id: ID статьи в БД
    """
    keyboard = InlineKeyboardBuilder()
    
    # Кнопка ссылки на статью
    keyboard.add(
        InlineKeyboardButton(
            text="🔗 Ссылка на статью",
            url=paper['url']
        )
    )
    
    # Кнопка удаления из библиотеки
    keyboard.add(
        InlineKeyboardButton(
            text="❌ Удалить",
            callback_data=f"delete_from_library:{paper_id}"
        )
    )
    
    # Кнопка добавления заметки
    keyboard.add(
        InlineKeyboardButton(
            text="📝 Добавить заметку",
            callback_data=f"add_note:{paper_id}"
        )
    )
    
    # Кнопка редактирования тегов
    keyboard.add(
        InlineKeyboardButton(
            text="🏷️ Редактировать теги",
            callback_data=f"edit_tags:{paper_id}"
        )
    )
    
    # Кнопка экспорта в BibTeX
    keyboard.add(
        InlineKeyboardButton(
            text="📁 Экспорт BibTeX",
            callback_data=f"export_bibtex:{paper_id}"
        )
    )
    
    keyboard.add(
        InlineKeyboardButton(
            text="📊 Суммаризация",
            callback_data=f"summary:{paper_id}"
        )
    )
    
    keyboard.adjust(2, 3)
    
    return keyboard

def create_library_navigation_keyboard(user_id: int, offset: int = 0, 
                                    total_count: int = 0, limit: int = 10) -> InlineKeyboardBuilder:
    """
    Создание клавиатуры для навигации по библиотеке
    
    Args:
        user_id: ID пользователя
        offset: Текущее смещение
        total_count: Общее количество статей
        limit: Количество статей на странице
    """
    keyboard = InlineKeyboardBuilder()
    
    has_prev = offset > 0
    has_next = offset + limit < total_count
    
    if has_prev:
        keyboard.add(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"library_page:{offset - limit}"
            )
        )
    
    current_page = (offset // limit) + 1
    total_pages = (total_count + limit - 1) // limit
    
    keyboard.add(
        InlineKeyboardButton(
            text=f"📄 {current_page}/{total_pages}",
            callback_data="current_page"
        )
    )
    
    if has_next:
        keyboard.add(
            InlineKeyboardButton(
                text="▶️ Вперед",
                callback_data=f"library_page:{offset + limit}"
            )
        )
    
    keyboard.row(
        InlineKeyboardButton(
            text="🔍 Поиск в библиотеке",
            callback_data="search_library"
        ),
        InlineKeyboardButton(
            text="📊 Статистика",
            callback_data="library_stats"
        )
    )
    
    keyboard.row(
        InlineKeyboardButton(
            text="📁 Экспорт BibTeX",
            callback_data="export_bibtex"
        ),
        InlineKeyboardButton(
            text="⚙️ Настройки",
            callback_data="library_settings"
        )
    )
    
    return keyboard
