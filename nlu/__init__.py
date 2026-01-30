"""
NLU (Natural Language Understanding) модуль.

Обеспечивает понимание пользовательских запросов:
- Классификация намерений (intents)
- Извлечение сущностей (entities)
- Управление контекстом диалога
- Роутинг между локальной и облачной LLM
"""

from .models import (
    Intent,
    IntentResult,
    Entity,
    EntityType,
    EntityExtractionResult,
    UserContext,
    ConversationTurn,
)
from .pipeline import NLUPipeline
from .context_manager import ContextManager

__all__ = [
    # Models
    "Intent",
    "IntentResult",
    "Entity",
    "EntityType",
    "EntityExtractionResult",
    "UserContext",
    "ConversationTurn",
    # Pipeline
    "NLUPipeline",
    "ContextManager",
]
