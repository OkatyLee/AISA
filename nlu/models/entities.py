"""Entity models for NLU."""

from enum import Enum
from typing import List, Optional, Any
from dataclasses import dataclass, field


class EntityType(Enum):
    """
    Типы сущностей для извлечения из текста.
    """
    # Поисковые сущности
    TOPIC = "topic"              # Тема поиска
    AUTHOR = "author"            # Автор статьи
    YEAR = "year"                # Год публикации
    YEAR_RANGE = "year_range"    # Диапазон лет (2020-2024)
    JOURNAL = "journal"          # Название журнала
    KEYWORD = "keyword"          # Ключевое слово
    
    # Идентификаторы статей
    URL = "url"                  # URL статьи
    DOI = "doi"                  # DOI идентификатор
    ARXIV_ID = "arxiv_id"        # arXiv ID
    PUBMED_ID = "pubmed_id"      # PubMed ID
    IEEE_ID = "ieee_id"          # IEEE ID
    
    # Ссылки на статьи в контексте
    ARTICLE_REF = "article_ref"  # Ссылка на статью ("первая", "статья 2", "эту")
    
    # Фильтры
    CITATION_COUNT = "citation_count"  # Минимальное число цитирований
    SOURCE = "source"            # Источник (arxiv, pubmed, ieee)
    
    # Количество
    COUNT = "count"              # Количество ("покажи 5 статей")


@dataclass
class Entity:
    """
    Сущность, извлечённая из текста.
    
    Attributes:
        type: Тип сущности
        value: Исходное значение из текста
        normalized_value: Нормализованное значение
        confidence: Уверенность в извлечении (0.0 - 1.0)
        start_pos: Начальная позиция в тексте
        end_pos: Конечная позиция в тексте
    """
    type: EntityType
    value: str
    confidence: float = 1.0
    start_pos: int = 0
    end_pos: int = 0
    normalized_value: Optional[Any] = None
    
    def __post_init__(self):
        if self.normalized_value is None:
            self.normalized_value = self._normalize()
    
    def _normalize(self) -> Any:
        """Нормализация значения в зависимости от типа."""
        if self.type == EntityType.YEAR:
            try:
                return int(self.value)
            except ValueError:
                return None
        elif self.type == EntityType.TOPIC:
            return self.value.lower().strip()
        elif self.type == EntityType.AUTHOR:
            return self.value.title().strip()
        elif self.type in {EntityType.CITATION_COUNT, EntityType.COUNT}:
            try:
                return int(self.value)
            except ValueError:
                return None
        elif self.type == EntityType.DOI:
            return self.value.strip().lower()
        elif self.type == EntityType.SOURCE:
            return self.value.strip().lower()
        return self.value


@dataclass
class EntityExtractionResult:
    """
    Результат извлечения сущностей.
    
    Attributes:
        entities: Список извлечённых сущностей
        raw_text: Исходный текст
        raw_response: Сырой ответ от LLM (для отладки)
    """
    entities: List[Entity] = field(default_factory=list)
    raw_text: str = ""
    raw_response: Optional[str] = None
    
    def get_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Получить все сущности определённого типа."""
        return [e for e in self.entities if e.type == entity_type]
    
    def get_first(self, entity_type: EntityType) -> Optional[Entity]:
        """Получить первую сущность определённого типа."""
        entities = self.get_by_type(entity_type)
        return entities[0] if entities else None
    
    def has_type(self, entity_type: EntityType) -> bool:
        """Проверить наличие сущности определённого типа."""
        return any(e.type == entity_type for e in self.entities)
    
    def to_search_params(self) -> dict:
        """Преобразовать в параметры поиска."""
        params = {}
        
        topic = self.get_first(EntityType.TOPIC)
        if topic:
            params["query"] = topic.normalized_value or topic.value
            
        author = self.get_first(EntityType.AUTHOR)
        if author:
            params["author"] = author.normalized_value or author.value
            
        year = self.get_first(EntityType.YEAR)
        if year:
            params["year"] = year.normalized_value or year.value
            
        source = self.get_first(EntityType.SOURCE)
        if source:
            params["source"] = source.normalized_value or source.value
            
        # Идентификаторы статей
        for id_type in [EntityType.DOI, EntityType.ARXIV_ID, EntityType.PUBMED_ID, EntityType.URL]:
            entity = self.get_first(id_type)
            if entity:
                params[id_type.value] = entity.normalized_value or entity.value
                
        return params
