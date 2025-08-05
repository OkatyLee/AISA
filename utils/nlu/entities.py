from enum import Enum
from typing import List, Optional, Any
from attr import dataclass

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
        type: Тип сущности (например, AUTHOR, TOPIC и т.д.)
        value: Значение сущности
        confidence: Уверенность в классификации (от 0 до 1)
        start_pos: Начальная позиция сущности в исходном тексте
        end_pos: Конечная позиция сущности в исходном тексте
        normalized_value: Дополнительное нормализованное значение (если применимо)
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
        entities: Список извлеченных сущностей
        raw_text: Исходный текст, из которого были извлечены сущности
    """
    entities: List[Entity]
    raw_text: str
    