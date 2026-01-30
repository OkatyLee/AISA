"""
LLM Services - унифицированный доступ к языковым моделям.

- OllamaClient: локальная LLM для быстрых задач (NLU, чат)
- OpenRouterClient: облачная LLM для тяжёлых задач (суммаризация, анализ)
- ChatService: сервис для общения в чате
- PaperService: сервис для работы со статьями
"""

from .client import LLMClient, OllamaClient, OpenRouterClient
from .chat_service import ChatService
from .paper_service import PaperService

__all__ = [
    "LLMClient",
    "OllamaClient", 
    "OpenRouterClient",
    "ChatService",
    "PaperService",
]
