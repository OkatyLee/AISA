"""
LLM-based Entity Extractor.

Извлекатель сущностей на базе локальной LLM (Ollama).
"""

import json
import logging
import re
from typing import Optional, List

from services.llm.client import OllamaClient, ChatMessage
from nlu.models import Entity, EntityType, EntityExtractionResult, UserContext
from utils.logger import setup_logger

logger = setup_logger(name="entity_extractor", level=logging.INFO)


ENTITY_EXTRACTION_PROMPT = """Ты — извлекатель сущностей для научного ассистента. Извлеки из текста ТОЛЬКО значимые сущности:

Типы сущностей:
- topic: ТОЛЬКО тема/предмет поиска БЕЗ служебных слов ("найди", "статьи", "по" и т.д.)
  Примеры:
  - "найди статьи по vibe coding" → topic: "vibe coding"
  - "статьи про машинное обучение" → topic: "машинное обучение"
  - "поиск neural networks" → topic: "neural networks"
- author: автор статьи (например: "Hinton", "Иванов")
- year: год публикации (например: "2023", "2024")
- source: источник (arxiv, pubmed, ieee)
- doi: DOI идентификатор (например: "10.1000/xyz")
- arxiv_id: arXiv ID (например: "2401.12345")
- url: ссылка на статью
- article_ref: ссылка на статью из списка ("первая", "вторая", "статья 2")
- count: количество ("5 статей", "10 результатов")

{context}

ВАЖНО: Для topic извлекай ТОЛЬКО саму тему поиска, без команд и служебных слов!

Ответь ТОЛЬКО в формате JSON:
{{"entities": [
    {{"type": "тип", "value": "значение", "confidence": 0.0-1.0}},
    ...
]}}

Если сущностей нет, верни: {{"entities": []}}"""


class LLMEntityExtractor:
    """
    Извлекатель сущностей на базе LLM.
    """
    
    def __init__(
        self,
        ollama_url: str = "http://ollama:11434",
        model: str = None,
    ):
        self.llm = OllamaClient(base_url=ollama_url, model=model)
        
    async def close(self):
        await self.llm.close()
    
    async def extract(
        self,
        text: str,
        context: Optional[UserContext] = None,
    ) -> EntityExtractionResult:
        """
        Извлечь сущности из текста.
        
        Args:
            text: Текст сообщения
            context: Контекст диалога
            
        Returns:
            EntityExtractionResult со списком сущностей
        """
        # Формируем контекст
        context_str = ""
        if context and context.current_articles:
            context_str = f"\nВ контексте {len(context.current_articles)} статей, пользователь может ссылаться на них по номеру."
        
        system_prompt = ENTITY_EXTRACTION_PROMPT.format(context=context_str)
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=f"Текст: {text}"),
        ]
        
        try:
            # Проверяем доступность Ollama
            if not await self.llm.is_available():
                logger.warning("Ollama недоступна, используем fallback")
                return self._fallback_extract(text)
            
            response = await self.llm.chat(messages, temperature=0.1, max_tokens=500)
            return self._parse_response(response.content, text)
            
        except Exception as e:
            logger.error(f"Ошибка извлечения сущностей: {e}")
            return self._fallback_extract(text)
    
    def _parse_response(self, response: str, original_text: str) -> EntityExtractionResult:
        """Парсинг ответа от LLM."""
        entities = []
        
        try:
            # Извлекаем JSON из ответа
            json_match = re.search(r'\{[^{}]*"entities"[^{}]*\[.*?\][^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                for entity_data in data.get("entities", []):
                    try:
                        entity_type = EntityType(entity_data["type"])
                        entity = Entity(
                            type=entity_type,
                            value=entity_data["value"],
                            confidence=float(entity_data.get("confidence", 0.8)),
                        )
                        entities.append(entity)
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Ошибка парсинга сущности: {e}")
                        continue
                        
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Ошибка парсинга JSON: {e}")
            # Пробуем fallback
            return self._fallback_extract(original_text)
        
        return EntityExtractionResult(
            entities=entities,
            raw_text=original_text,
            raw_response=response,
        )
    
    def _fallback_extract(self, text: str) -> EntityExtractionResult:
        """
        Fallback извлечение на основе регулярных выражений.
        """
        entities = []
        text_lower = text.lower()
        
        # Извлекаем год
        year_patterns = [
            r'\b(20[0-2][0-9])\b',  # 2000-2029
            r'за (\d{4}) год',
            r'в (\d{4}) году',
        ]
        for pattern in year_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                entities.append(Entity(
                    type=EntityType.YEAR,
                    value=match,
                    confidence=0.9,
                ))
        
        # Извлекаем DOI
        doi_pattern = r'(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)'
        doi_matches = re.findall(doi_pattern, text)
        for match in doi_matches:
            entities.append(Entity(
                type=EntityType.DOI,
                value=match,
                confidence=0.95,
            ))
        
        # Извлекаем arXiv ID
        arxiv_pattern = r'(\d{4}\.\d{4,5})(?:v\d+)?'
        arxiv_matches = re.findall(arxiv_pattern, text)
        for match in arxiv_matches:
            entities.append(Entity(
                type=EntityType.ARXIV_ID,
                value=match,
                confidence=0.95,
            ))
        
        # Извлекаем URL
        url_pattern = r'(https?://\S+)'
        url_matches = re.findall(url_pattern, text)
        for match in url_matches:
            entities.append(Entity(
                type=EntityType.URL,
                value=match,
                confidence=0.95,
            ))
        
        # Извлекаем ссылки на статьи
        ref_patterns = [
            (r'(перв\w+)\s*стать', 'первая'),
            (r'(втор\w+)\s*стать', 'вторая'),
            (r'(треть\w+)\s*стать', 'третья'),
            (r'стать[яюией]*\s*(\d+)', None),
            (r'номер\s*(\d+)', None),
        ]
        for pattern, normalized in ref_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                entities.append(Entity(
                    type=EntityType.ARTICLE_REF,
                    value=normalized or match,
                    confidence=0.8,
                ))
        
        # Извлекаем источники
        sources = ['arxiv', 'pubmed', 'ieee', 'semantic scholar']
        for source in sources:
            if source in text_lower:
                entities.append(Entity(
                    type=EntityType.SOURCE,
                    value=source,
                    confidence=0.9,
                ))
        
        # Извлекаем известные топики (академические ключевые слова)
        topics = {
            'машинное обучение': 'machine learning',
            'машинного обучения': 'machine learning',
            'machine learning': 'machine learning',
            'deep learning': 'deep learning',
            'глубокое обучение': 'deep learning',
            'нейронные сети': 'neural networks',
            'neural networks': 'neural networks',
            'nlp': 'nlp',
            'обработка естественного языка': 'nlp',
            'computer vision': 'computer vision',
            'компьютерное зрение': 'computer vision',
            'трансформеры': 'transformers',
            'transformers': 'transformers',
            'bert': 'bert',
            'gpt': 'gpt',
            'llm': 'llm',
        }
        
        for topic, normalized in topics.items():
            if topic in text_lower:
                entities.append(Entity(
                    type=EntityType.TOPIC,
                    value=topic,
                    confidence=0.85,
                    normalized_value=normalized,
                ))
                break  # Берём только первый найденный топик
        
        # Если не нашли известный топик, пробуем извлечь из паттернов
        if not any(e.type == EntityType.TOPIC for e in entities):
            topic_patterns = [
                # Паттерны с "по" (самые частые)
                r'статьи?\s+по\s+(.+?)(?:\s+за\s+\d|\s+от\s+автора|\s+в\s+\d|$)',
                r'(?:найди|найти|поищи|искать|ищи)\s+(?:статьи?\s+)?по\s+(.+?)(?:\s+за\s+\d|\s+от|$)',
                r'\bпо\s+(?:теме\s+)?(.+?)(?:\s+за\s+\d|\s+в\s+\d|\s+от|$)',
                # Паттерны с "про"
                r'(?:статьи?\s+)?про\s+(.+?)(?:\s+за\s+\d|\s+в\s+\d|\s+от\s+автора|$)',
                # Паттерны с "на тему"
                r'на\s+тему\s+(.+?)(?:\s+за\s+\d|\s+в\s+\d|$)',
                # Паттерн "поиск X"
                r'поиск\s+(.+?)(?:\s+за\s+\d|\s+в\s+\d|$)',
            ]
            for pattern in topic_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    topic = match.group(1).strip()
                    # Удаляем trailing служебные слова
                    topic = re.sub(r'\s+(статьи?|статей)\s*$', '', topic)
                    if len(topic) > 2 and len(topic) < 100:
                        entities.append(Entity(
                            type=EntityType.TOPIC,
                            value=topic,
                            confidence=0.7,
                        ))
                        break
        
        return EntityExtractionResult(
            entities=entities,
            raw_text=text,
        )
