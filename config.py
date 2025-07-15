from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str
    LOG_LEVEL: str
    LOG_FILE: str
    MAX_RESULTS: int
    MAX_REQUESTS_PER_HOUR: int
    MAX_REQUESTS_PER_MINUTE: int

def load_config() -> Config:
    import os
    from dotenv import load_dotenv

    load_dotenv()

    return Config(
        BOT_TOKEN=os.getenv("BOT_TOKEN"),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        LOG_FILE=os.getenv("LOG_FILE", "bot.log"),
        MAX_RESULTS=os.getenv("MAX_RESULTS", 5),
        MAX_REQUESTS_PER_HOUR=int(os.getenv("MAX_REQUESTS_PER_HOUR", 100)),
        MAX_REQUESTS_PER_MINUTE=int(os.getenv("MAX_REQUESTS_PER_MINUTE", 10))
    )