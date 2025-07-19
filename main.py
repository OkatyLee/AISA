import asyncio
import logging
import os
import signal
import sys
from bot import create_bot
from utils import setup_logger
from utils.metrics import metrics

# Настройка логирования с ротацией
logger = setup_logger(
    name="bot_logger", 
    log_file="logs/bot.log", 
    level=logging.INFO
)

class GracefulBot:
    """Класс для корректного управления жизненным циклом бота"""
    
    def __init__(self):
        self.bot = None
        self.dp = None
        self.is_running = False
    
    async def startup(self):
        """Инициализация и запуск бота"""
        try:
            logger.info("Инициализация бота...")
            self.bot, self.dp = create_bot()
            
            logger.info("Бот успешно инициализирован")
            self.is_running = True
            
            # Запуск polling
            logger.info("Запуск polling...")
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
            await self.shutdown()
            raise
    
    async def shutdown(self):
        """Корректное завершение работы бота"""
        if not self.is_running:
            return
            
        logger.info("Завершение работы бота...")
        self.is_running = False
        
        try:
            # Закрываем сессию бота
            if self.bot and hasattr(self.bot, 'session'):
                await self.bot.session.close()
                logger.info("Сессия бота закрыта")
            
            # Логируем финальную статистику
            metrics.log_daily_stats()
            logger.info("Бот успешно завершил работу")
            
        except Exception as e:
            logger.error(f"Ошибка при завершении работы: {e}", exc_info=True)

async def main():
    """Главная функция с улучшенной обработкой ошибок"""
    # Создание необходимых директорий
    for directory in ['logs', 'db']:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Создана директория: {directory}")
    
    bot_instance = GracefulBot()
    
    # Обработчик сигналов для корректного завершения
    def signal_handler(sig, frame):
        logger.info(f"Получен сигнал {sig}. Завершение работы...")
        asyncio.create_task(bot_instance.shutdown())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot_instance.startup()
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}", exc_info=True)
    finally:
        await bot_instance.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа прервана пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка приложения: {e}", exc_info=True)
        sys.exit(1)