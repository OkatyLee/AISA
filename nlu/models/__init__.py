"""NLU Models - dataclasses для работы с NLU."""

from .intents import Intent, IntentResult
from .entities import Entity, EntityType, EntityExtractionResult
from .context import UserContext, ConversationTurn

__all__ = [
    "Intent",
    "IntentResult",
    "Entity",
    "EntityType",
    "EntityExtractionResult",
    "UserContext",
    "ConversationTurn",
]
