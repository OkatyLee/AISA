from utils.nlu.entities import Entity, EntityType, EntityExtractionResult
from typing import Dict, List
from re import Pattern
import re

class RuleBasedEntityClassifier:
    """
    Правило-ориентированный классификатор сущностей.
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
                re.compile(r'с (\d{4}) по (\d{4})')  # Этот паттерн имеет 2 группы!
            ],
            EntityType.AUTHOR: [
                re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'),  # Улучшенный паттерн для составных имен
                re.compile(r'\b([А-Я][а-я]+(?:\s+[А-Я][а-я]+)+)\b'),  # То же для русских имен
                re.compile(r'статьи ([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*)', re.IGNORECASE),
                re.compile(r'работы ([А-Я][а-я]+(?:\s+[А-Я][а-я]+)*)', re.IGNORECASE)
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
            ]
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
   
    def classify(self, text: str) -> EntityExtractionResult:
        """
        Классификация текста на основе правил
       
        Args:
            text: Входной текст
           
        Returns:
            EntityExtractionResult с найденными сущностями
        """
        entities = []
        
        # Извлекаем сущности по регулярным выражениям
        for entity_type, patterns in self.patterns.items():
            for pattern in patterns:
                matches = pattern.finditer(text)
                for match in matches:
                    # Обрабатываем случай с несколькими группами захвата
                    if entity_type == EntityType.YEAR and match.groups() and len(match.groups()) > 1:
                        # Для паттерна "с YYYY по YYYY" создаем две сущности
                        for i, group in enumerate(match.groups()):
                            if group and group.isdigit():
                                entity = Entity(
                                    type=entity_type,
                                    value=group,
                                    confidence=1.0,
                                    start_pos=match.start(i+1),
                                    end_pos=match.end(i+1)
                                )
                                entities.append(entity)
                    else:
                        # Стандартная обработка
                        value = match.group(1).strip() if match.groups() else match.group().strip()
                        entity = Entity(
                            type=entity_type,
                            value=value,
                            confidence=1.0,
                            start_pos=match.start(1) if match.groups() else match.start(),
                            end_pos=match.end(1) if match.groups() else match.end()
                        )
                        entities.append(entity)
        
        # Добавляем ключевые слова
        keyword_entities = self._extract_keywords(text)
        entities.extend(keyword_entities)
        
        # Удаляем дублирующиеся сущности
        entities = self._remove_duplicates(entities)
       
        return EntityExtractionResult(entities=entities, raw_text=text)
    
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


