
from nlp import (
    RuleBasedEntityExtractor,
    RuleBasedIntentClassifier,
    ContextManager,
    QueryProcessor
)
from nlp.query_processor import QueryProcessingResult

class NLUPipeline:
    """
    Класс для обработки пользовательских запросов с использованием NLU.
    
    Этот класс объединяет классификатор намерений и извлечение сущностей для обработки текстовых запросов.
    
    Attributes:
        intent_classifier: RuleBasedIntentClassifier
            Классификатор намерений, использующий правила для определения намерения пользователя
        entity_classifier: RuleBasedEntityExtractor
            Классификатор сущностей, использующий правила для извлечения сущностей из текста
    """
    
    def __init__(self):
        self.context_manager = ContextManager()
        self.query_processor = QueryProcessor()
        
    async def process_message(self, user_id: int, message: str) -> QueryProcessingResult:
        """
        Обрабатывает сообщение пользователя, классифицируя намерение и извлекая сущности.
        
        Args:
            user_id: Идентификатор пользователя
            message: Текст сообщения пользователя
            
        Returns:
            QueryProcessingResult с результатами обработки
        """
        # Получаем контекст пользователя
        normalized_text = self.preprocess_text(message)
        
        context = await self.context_manager.get_user_context(user_id)
        
        # Обрабатываем запрос
        result = self.query_processor.process(normalized_text, context)
        
        # Обновляем контекст пользователя
        await self.context_manager.update_user_context(
            user_id,
            message,
            result.intent,
            result.entities.entities,
            bot_response=None,  # Здесь можно добавить ответ бота, если требуется
            search_results=None  # Здесь можно добавить результаты поиска, если есть
        )
        
        return result   
    
    def preprocess_text(self, text: str) -> str:
        """
        Предобрабатывает текст запроса пользователя.
        
        Args:
            text: Текст запроса пользователя
            
        Returns:
            str: Предобработанный текст
        """
        # Здесь можно добавить логику предобработки текста, например, удаление лишних пробелов,
        # приведение к нижнему регистру и т.д.
        import re
        text = re.sub(r'\s+', ' ', text.strip())
        text = text.lower()
        return text