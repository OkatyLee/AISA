from aiogram import Bot, Dispatcher
from config.config import load_config
from config.constants import OLLAMA_BASE_URL
from typing import Tuple
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from middlewares import Middleware
from handlers import register_handlers, init_chat_services, close_chat_services


def create_bot() -> Tuple[Bot, Dispatcher]:
    
    config = load_config()
    
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    dp = Dispatcher()
    dp.message.middleware(Middleware(config))
    
    register_handlers(dp)
    
    # Добавляем lifecycle hooks для инициализации и закрытия сервисов
    @dp.startup()
    async def on_startup():
        await init_chat_services(
            ollama_url=OLLAMA_BASE_URL,
            db_path="db/scientific_assistant.db"
        )
    
    @dp.shutdown()
    async def on_shutdown():
        await close_chat_services()
    
    return bot, dp