from aiogram import Dispatcher
from . import comands, messages

def register_handlers(dp: Dispatcher):

    comands.register_command_handlers(dp)
    messages.register_message_handlers(dp)
