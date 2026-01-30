from aiogram import Dispatcher
from . import commands, library_callbacks, search_commands, pagination_callbacks
from .chat_handler import register_chat_handler, init_chat_services, close_chat_services

def register_handlers(dp: Dispatcher):
    
    library_callbacks.register_library_handlers(dp)
    pagination_callbacks.register_pagination_handlers(dp)
    commands.register_command_handlers(dp)
    search_commands.register_search_handlers(dp)
    # Используем новый chat_handler вместо старого messages
    register_chat_handler(dp)


# Экспортируем функции инициализации
__all__ = [
    "register_handlers",
    "init_chat_services",
    "close_chat_services",
]
    
