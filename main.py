import asyncio
import logging
import os
from bot import create_bot
from utils import setup_logger

# Настройка логирования
if not os.path.exists('logs'):
    os.makedirs('logs')

logger = setup_logger(
    name="bot_logger",
    log_file="logs/bot.log",
    level=logging.INFO
)


async def main():
    """Главная функция запуска бота"""
    bot = None
    try:
        bot, dp = create_bot()
        logger.info("Бот запущен")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        if bot and hasattr(bot, 'session'):
            await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())