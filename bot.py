from aiogram import Bot, Dispatcher
from config.config import load_config
from typing import Tuple
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from middlewares import Middleware
from handlers import register_handlers


def create_bot() -> Tuple[Bot, Dispatcher]:
    
    config = load_config()
    
    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.message.middleware(Middleware(config))
    
    register_handlers(dp)
    
    return bot, dp