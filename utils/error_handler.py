"""
Централизованная обработка ошибок для бота
"""

from typing import Optional, Dict, Any
from aiogram.types import Message, CallbackQuery
from utils import setup_logger
from config.messages import ERROR_MESSAGES, EMOJI

logger = setup_logger(name="error_handler", level="ERROR")

class ErrorHandler:
    """Класс для централизованной обработки ошибок"""
    
    @staticmethod
    async def handle_search_error(
        message: Message, 
        error: Exception, 
        status_message: Optional[Message] = None
    ):
        """Обработка ошибок поиска"""
        logger.error(f"Search error for user {message.from_user.id}: {error}")
        
        # Удаляем сообщение о статусе если есть
        if status_message:
            try:
                await status_message.delete()
            except:
                pass
        
        error_text = (
            f"{ERROR_MESSAGES['search_failed']}\n\n"
            f"🔄 Попробуйте еще раз через несколько секунд.\n\n"
            f"🔧 **Возможные причины:**\n"
            f"• Временная недоступность ArXiv API\n"
            f"• Проблемы с интернет-соединением\n"
            f"• Превышение лимита запросов\n\n"
            f"💬 Если проблема повторяется, обратитесь к администратору."
        )
        
        await message.answer(error_text, parse_mode="Markdown")
    
    @staticmethod
    async def handle_library_error(message: Message, error: Exception):
        """Обработка ошибок библиотеки"""
        logger.error(f"Library error for user {message.from_user.id}: {error}")
        
        error_text = (
            f"{ERROR_MESSAGES['library_failed']}\n\n"
            f"{EMOJI['error']} Попробуйте еще раз через несколько секунд.\n"
            f"{EMOJI['info']} Если проблема повторяется, обратитесь к администратору."
        )
        
        await message.answer(error_text, parse_mode="Markdown")
    
    @staticmethod
    async def handle_database_error(message: Message, error: Exception, operation: str):
        """Обработка ошибок базы данных"""
        logger.error(f"Database error for user {message.from_user.id} during {operation}: {error}")
        
        if operation == "save":
            error_text = ERROR_MESSAGES['save_failed']
        elif operation == "delete":
            error_text = ERROR_MESSAGES['delete_failed']
        else:
            error_text = f"{EMOJI['error']} Произошла ошибка при работе с базой данных"
        
        await message.answer(error_text)
    
    @staticmethod
    async def handle_validation_error(message: Message, error_message: str):
        """Обработка ошибок валидации"""
        await message.answer(f"{EMOJI['warning']} {error_message}")
        
    @staticmethod
    async def handle_stats_error(message: Message, error: Exception):
        """Обработка ошибок статистики"""
        logger.error(f"Stats error for user {message.from_user.id}: {error}")

        error_text = (
            f"{ERROR_MESSAGES['stats_failed']}\n\n"
            f"🔄 Попробуйте еще раз через несколько секунд.\n\n"
            f"🔧 **Возможные причины:**\n"
            f"• Временная недоступность ArXiv API\n"
            f"• Проблемы с интернет-соединением\n"
            f"• Превышение лимита запросов\n\n"
            f"💬 Если проблема повторяется, обратитесь к администратору."
        )

        await message.answer(error_text, parse_mode="Markdown")
        
    @staticmethod   
    async def handle_summarization_error(callback: CallbackQuery, error: Exception):
        """Обработка ошибок суммаризации"""
        logger.error(f"Summarization error for user {callback.from_user.id}: {error}")

        error_text = (
            f"{EMOJI['error']} Произошла ошибка при суммаризации статьи.\n\n"
            f"🔄 Попробуйте еще раз через несколько секунд.\n\n"
            f"💬 Если проблема повторяется, обратитесь к администратору."
        )
        
        await callback.message.answer(error_text, parse_mode="Markdown")

    @staticmethod
    def log_unexpected_error(context: str, error: Exception, user_data: Optional[Dict[str, Any]] = None):
        """Логирование неожиданных ошибок"""
        log_message = f"Unexpected error in {context}: {error}"
        if user_data:
            log_message += f" | User data: {user_data}"
        logger.error(log_message, exc_info=True)
