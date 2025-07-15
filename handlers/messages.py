from aiogram import Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from utils import InputValidator

validator = InputValidator()

def register_message_handlers(dp: Dispatcher):
    
    dp.message.register(message_handler, F.text)

async def message_handler(message: Message):
    
    text = validator.sanitize_text(message.text)

    if validator.contains_suspicious_content(text):
        await message.answer(
            "⚠️ Сообщение содержит потенциально небезопасный контент. "
            "Пожалуйста, будьте осторожны."
        )
        return

    await message.answer("Вы написали: " + text)