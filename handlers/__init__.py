from aiogram import Dispatcher
from . import commands, library_callbacks, messages, search_commands, pagination_callbacks

def register_handlers(dp: Dispatcher):
    
    library_callbacks.register_library_handlers(dp)
    pagination_callbacks.register_pagination_handlers(dp)
    commands.register_command_handlers(dp)
    search_commands.register_search_handlers(dp)
    messages.register_message_handlers(dp)
    
