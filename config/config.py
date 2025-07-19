from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    """Конфигурация приложения из переменных окружения"""
    # Секреты
    BOT_TOKEN: str
    
    # Настройки логирования
    LOG_LEVEL: str
    LOG_FILE: str
    
    # API лимиты
    MAX_RESULTS: int
    MAX_REQUESTS_PER_HOUR: int
    MAX_REQUESTS_PER_MINUTE: int
    
    # База данных
    DB_PATH: str
    
    # Кэширование
    CACHE_TTL_MINUTES: int
    MAX_CACHE_SIZE: int

def load_config() -> Config:
    """
    Загрузка конфигурации из переменных окружения
    
    Returns:
        Config: Объект конфигурации
        
    Raises:
        ValueError: Если не найдена обязательная переменная
    """
    import os
    from dotenv import load_dotenv

    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("BOT_TOKEN is required but not found in environment variables")

    return Config(
        BOT_TOKEN=bot_token,
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        LOG_FILE=os.getenv("LOG_FILE", "logs/bot.log"),
        MAX_RESULTS=int(os.getenv("MAX_RESULTS", "5")),
        MAX_REQUESTS_PER_HOUR=int(os.getenv("MAX_REQUESTS_PER_HOUR", "100")),
        MAX_REQUESTS_PER_MINUTE=int(os.getenv("MAX_REQUESTS_PER_MINUTE", "10")),
        DB_PATH=os.getenv("DB_PATH", "db/scientific_assistant.db"),
        CACHE_TTL_MINUTES=int(os.getenv("CACHE_TTL_MINUTES", "15")),
        MAX_CACHE_SIZE=int(os.getenv("MAX_CACHE_SIZE", "100"))
    )