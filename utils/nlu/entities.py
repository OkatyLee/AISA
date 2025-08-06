from enum import Enum
from typing import List, Optional, Any
from dataclasses import dataclass

class EntityType(Enum):
    """Типы сущностей для извлечения информации.

    Attributes:
        AUTHOR: Автор статьи
        TOPIC: Тематика статьи
        YEAR: Год публикации
        JOURNAL: Название журнала
        ARTICLE_TITLE: Заголовок статьи
        INSTITUTION: Учебное заведение или организация
        KEYWORD: Ключевые слова статьи
        DATE_RANGE: Диапазон дат
        CITATION_COUNT: Количество цитирований статьи
    """
    AUTHOR = "author"
    TOPIC = "topic"
    YEAR = "year"
    JOURNAL = "journal"
    ARTICLE_TITLE = "article_title"
    INSTITUTION = "institution"
    KEYWORD = "keyword"
    DATE_RANGE = "date_range"
    CITATION_COUNT = "citation_count"


@dataclass
class Entity:
    """
    Представляет сущность, извлеченную из текста.
    Attributes:
        type: EntityType
            Тип сущности (например, AUTHOR, TOPIC и т.д.)
        value: str
            Значение сущности
        confidence: float
            Уверенность в классификации (от 0 до 1)
        start_pos: int
            Начальная позиция сущности в исходном тексте
        end_pos: int
            Конечная позиция сущности в исходном тексте
        normalized_value: Optional[Any]
            Дополнительное нормализованное значение (если применимо)
    """
    type: EntityType
    value: str
    confidence: float
    start_pos: int
    end_pos: int
    normalized_value: Optional[Any] = None
    
@dataclass
class EntityExtractionResult:
    """
    Результат извлечения сущностей из текста.
    Attributes:
        entities: List[Entity]
            Список извлеченных сущностей
        raw_text: str
            Исходный текст, из которого были извлечены сущности
    """
    entities: List[Entity]
    raw_text: str
    