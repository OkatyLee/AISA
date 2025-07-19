from aiogram import Dispatcher
from . import comands, library_callbacks, messages

def register_handlers(dp: Dispatcher):

    comands.register_command_handlers(dp)
    messages.register_message_handlers(dp)
    library_callbacks.register_library_handlers(dp)
    
