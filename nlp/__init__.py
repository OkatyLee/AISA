"""
DEPRECATED: Этот модуль устарел.
Используйте новый модуль `nlu` вместо `nlp`.

Пример миграции:
    # Старый код:
    from nlp import RuleBasedIntentClassifier
    
    # Новый код:
    from nlu import NLUPipeline, Intent
    from nlu.classifiers import LLMIntentClassifier
"""
import warnings
warnings.warn(
    "Модуль 'nlp' устарел. Используйте 'nlu' вместо него.",
    DeprecationWarning,
    stacklevel=2
)

from .intent_classifier import RuleBasedIntentClassifier
from .entity_classifier import RuleBasedEntityExtractor
from .query_processor import QueryProcessor
from .context_manager import ContextManager
from .nlu_pipeline import NLUPipeline