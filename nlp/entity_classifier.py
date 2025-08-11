from utils.nlu.intents import Intent
from utils.nlu.entities import Entity, EntityType, EntityExtractionResult
from typing import Any, Dict, List
from re import Pattern
import re

class RuleBasedEntityExtractor:
    """
    Правило-ориентированный извлекатель сущностей.
    Использует регулярные выражения для извлечения сущностей из текста.
    """
    
    def __init__(self):
        self.patterns = self._compile_patterns()
        self.academic_keywords = self._load_academic_keywords()
        self.common_authors = self._load_common_authors()
        self.journals = self._load_journals()
    
    def _compile_patterns(self) -> Dict[EntityType, List[Pattern]]:
        return {
            EntityType.YEAR: [
                re.compile(r'\b(19|20)\d{2}\b'),  # Группа захвата всего года
                re.compile(r'за (\d{4}) год'),
                re.compile(r'в (\d{4}) году'),
                re.compile(r'с (\d{4}) по (\d{4})'),  # Этот паттерн имеет 2 группы!
                re.compile(r'(\d{4})\s*год'),  # 2023 год
                re.compile(r'год[а-я]*\s*(\d{4})'),  # года 2023
                re.compile(r'статьи за (\d{4})'),  # статьи за 2023
                re.compile(r'публикации (\d{4}) года'),  # публикации 2023 года
            ],
            EntityType.AUTHOR: [
                re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'),  # Улучшенный паттерн для составных имен
                re.compile(r'\b([А-Я][а-я]+(?:\s+[А-Я][а-я]+)+)\b'),  # То же для русских имен
                re.compile(r'статьи ([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*)', re.IGNORECASE),
                re.compile(r'работы ([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*)', re.IGNORECASE),
                re.compile(r'от автора\s+([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*)', re.IGNORECASE),  # от автора Smith
                re.compile(r'papers by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', re.IGNORECASE),  # papers by Smith
                re.compile(r'публикации\s+([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*)', re.IGNORECASE),  # публикации Иванова
                re.compile(r'исследования\s+(?:автора\s+)?([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*)', re.IGNORECASE)  # исследования автора Петров
            ],
            EntityType.TOPIC: [
                # Используем жадный квантификатор и улучшаем границы
                re.compile(r'про ([\w\s]+?)(?=\s+(?:за|в|статьи|автор)|$)', re.IGNORECASE),
                re.compile(r'по (?:теме|темам)?\s*([\w\s]+?)(?=\s+(?:за|в|статьи|автор)|$)', re.IGNORECASE),
                re.compile(r'на (?:тему|темы)\s+([\w\s]+?)(?=\s+(?:за|в|статьи|автор)|$)', re.IGNORECASE),
                re.compile(r'в области ([\w\s]+?)(?=\s+(?:за|в|статьи|автор)|$)', re.IGNORECASE)
            ],
            EntityType.CITATION_COUNT: [
                re.compile(r'более (\d+) цитирований'),
                re.compile(r'больше (\d+) раз цитируем'),
                re.compile(r'цитируем[ыхао]+ более (\d+)')
            ],
            # URL и идентификаторы
            EntityType.URL: [
                re.compile(r'(https?://\S+)', re.IGNORECASE),
            ],
            EntityType.DOI: [
                # doi:10.1000/xyz123 или просто 10.1000/xyz123
                re.compile(r'(?:doi\s*[:]?\s*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', re.IGNORECASE),
            ],
            EntityType.ARXIV_ID: [
                # arXiv:2401.12345 или 2401.12345
                re.compile(r'(?:arxiv\s*[:]?\s*)?(\d{4}\.\d{4,5})(?:v\d+)?', re.IGNORECASE),
            ],
            EntityType.PUBMED_ID: [
                # PMID: 12345678 или pubmed 12345678
                re.compile(r'(?:pmid|pubmed)\s*[:]?\s*(\d{5,9})', re.IGNORECASE),
            ],
            EntityType.IEEE_ID: [
                # IEEE document id
                re.compile(r'(?:ieee|document)\s*[:#]?\s*(\d{5,9})', re.IGNORECASE),
            ],
        }
    
    def _load_academic_keywords(self) -> List[str]:
        """Загружает список академических ключевых слов."""
        return {
            'машинное обучение', 'machine learning', 'deep learning', 'нейронные сети',
            'neural networks', 'computer vision', 'natural language processing', 'nlp',
            'artificial intelligence', 'ai', 'data science', 'big data',
            'reinforcement learning', 'supervised learning', 'unsupervised learning',
            'трансформеры', 'transformers', 'bert', 'gpt', 'llm', 'генеративные модели'
        }
    
    def _load_common_authors(self) -> List[str]:
        """Загружает список часто встречающихся авторов."""
        return {
            'Geoffrey Hinton', 'Yann LeCun', 'Yoshua Bengio', 'Andrew Ng',
            'Ian Goodfellow', 'Ilya Sutskever', 'Jeff Dean', 'Andrej Karpathy',
            'Хинтон', 'Лекун', 'Бенжио'
        }
    
    def _load_journals(self) -> List[str]:
        """Загружает список известных журналов."""
        return {
            'Nature', 'Science', 'ICML', 'NeurIPS', 'ICLR', 'AAAI', 'IJCAI',
            'IEEE', 'ACM', 'arXiv', 'Journal of Machine Learning Research'
        }
    
    
    def _extract_keywords(self, text: str) -> List[Entity]:
        """Извлекает ключевые слова из текста."""
        entities = []
        text_lower = text.lower()
        
        for keyword in self.academic_keywords:
            keyword_lower = keyword.lower()
            start = 0
            while True:
                pos = text_lower.find(keyword_lower, start)
                if pos == -1:
                    break
                
                # Проверяем границы слов
                if (pos == 0 or not text[pos-1].isalnum()) and \
                   (pos + len(keyword) == len(text) or not text[pos + len(keyword)].isalnum()):
                    entity = Entity(
                        type=EntityType.KEYWORD,
                        value=text[pos:pos + len(keyword)],  # Сохраняем оригинальный регистр
                        confidence=0.9,
                        start_pos=pos,
                        end_pos=pos + len(keyword)
                    )
                    entities.append(entity)
                
                start = pos + 1
        
        return entities
    
    async def extract(self, text: str, intent: Intent) -> EntityExtractionResult:
        entities: List[Entity] = []

        # Извлекаем сущности по паттернам
        for entity_type, patterns in self.patterns.items():
            for pattern in patterns:
                matches = pattern.finditer(text)
                for match in matches:
                    entity = Entity(
                        type=entity_type,
                        value=match.group(1) if match.groups() else match.group(0),
                        confidence=0.8,
                        start_pos=match.start(),
                        end_pos=match.end()
                    )
                    # Нормализация значений
                    entity.normalized_value = self._normalize_entity(entity)
                    entities.append(entity)

        # Извлекаем топики и авторов по словарю
        entities.extend(self._extract_topics_by_dictionary(text))
        entities.extend(self._extract_authors_by_dictionary(text))

        # Постобработка и дедупликация
        entities = self._post_process_entities(entities)

        return EntityExtractionResult(entities=entities, raw_text=text)
    
    def _extract_topics_by_dictionary(self, text: str) -> List[Entity]:
        entities = []
        text_lower = text.lower()
        
        for keyword in self.academic_keywords:
            if keyword.lower() in text_lower:
                start_pos = text_lower.find(keyword.lower())
                entity = Entity(
                    type=EntityType.TOPIC,
                    value=keyword,
                    confidence=0.9,
                    start_pos=start_pos,
                    end_pos=start_pos + len(keyword),
                    normalized_value=keyword.lower()
                )
                entities.append(entity)
        
        return entities
    
    def _extract_authors_by_dictionary(self, text: str) -> List[Entity]:
        entities = []
        
        for author in self.common_authors:
            if author.lower() in text.lower():
                start_pos = text.lower().find(author.lower())
                entity = Entity(
                    type=EntityType.AUTHOR,
                    value=author,
                    confidence=0.95,
                    start_pos=start_pos,
                    end_pos=start_pos + len(author),
                    normalized_value=author
                )
                entities.append(entity)
        
        return entities
    
    def _remove_duplicates(self, entities: List[Entity]) -> List[Entity]:
        """Удаляет дублирующиеся сущности."""
        seen = set()
        unique_entities = []
        
        for entity in entities:
            key = (entity.type, entity.value.lower(), entity.start_pos, entity.end_pos)
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)
        
        return unique_entities
    
    def _normalize_entity(self, entity: Entity) -> Any:
        """Нормализация извлеченных сущностей"""
        if entity.type == EntityType.YEAR:
            try:
                return int(entity.value)
            except ValueError:
                return None
        
        elif entity.type == EntityType.TOPIC:
            return entity.value.lower().strip()
        
        elif entity.type == EntityType.AUTHOR:
            return entity.value.title().strip()
        
        elif entity.type == EntityType.CITATION_COUNT:
            try:
                return int(entity.value)
            except ValueError:
                return None

        elif entity.type == EntityType.URL:
            return entity.value.strip()

        elif entity.type == EntityType.DOI:
            return entity.value.strip().lower()

        elif entity.type == EntityType.ARXIV_ID:
            return entity.value.strip()

        elif entity.type == EntityType.PUBMED_ID:
            try:
                return int(entity.value)
            except ValueError:
                return None

        elif entity.type == EntityType.IEEE_ID:
            try:
                return int(entity.value)
            except ValueError:
                return None
        
        return entity.value
    
    def _post_process_entities(self, entities: List[Entity]) -> List[Entity]:
        """Постобработка и дедупликация сущностей"""
        # Удаляем дубликаты
        seen = set()
        deduplicated = []
        
        for entity in entities:
            key = (entity.type, entity.normalized_value)
            if key not in seen:
                seen.add(key)
                deduplicated.append(entity)
        
        # Сортируем по позиции в тексте
        deduplicated.sort(key=lambda e: e.start_pos)
        
        return deduplicated


