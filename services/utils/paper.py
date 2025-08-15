
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
import hashlib

import dateutil


class Paper:
    """
    Класс, представляющий научную статью.
    Attributes:
        title: Заголовок статьи
        authors: Список авторов статьи
        abstract: Аннотация статьи
        doi: DOI статьи
        publication_date: Дата публикации статьи
        journal: Название журнала, в котором опубликована статья
        keywords: Ключевые слова статьи
        url: URL статьи
        external_id: Внешний идентификатор статьи (например, arxiv_id, pubmed_id, ieee_id)
        source: Источник статьи (arxiv, pubmed, ieee и т.д.)
        source_metadata: Дополнительные метаданные источника
    """
    def __init__(self, title: str = '', authors: List[str] = None,
                abstract: str = '', doi: str = '', publication_date: Optional[datetime] = None,
                journal: str = '', keywords: List[str] = None, url: str = '',
                external_id: str = '', source: str = '', source_metadata: Dict[str, Any] = None,
                semantic_score: float = 0.0):
        self.title = title or ''
        self.authors = authors if authors is not None else []
        self.abstract = abstract or ''
        self.doi = doi or ''
        self.publication_date = publication_date
        self.journal = journal or ''
        self.keywords = keywords if keywords is not None else []
        self.url = url or ''
        self.external_id = external_id or ''
        self.source = source or ''
        self.source_metadata = source_metadata or {}
        self.semantic_score = semantic_score

    def to_dict(self):
        return {
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "doi": self.doi,
            "publication_date": self.publication_date,
            "journal": self.journal,
            "keywords": self.keywords,
            "url": self.url,
            "external_id": self.external_id,
            "source": self.source,
            "source_metadata": self.source_metadata
        }   
        
    def __getitem__(self, key):
        return getattr(self, key, None) 

    @property
    def arxiv_id(self):
        return self.external_id if self.source == 'arxiv' else None
    
    @property
    def pubmed_id(self):
        return self.external_id if self.source == 'pubmed' else None
    
    @property
    def ieee_id(self):
        return self.external_id if self.source == 'ieee' else None 
    
    def get_safe_callback_data(self, prefix: str = "paper", max_length: int = 60) -> str:
        """
        Возвращает безопасные данные для callback_data кнопки Telegram.
        
        :param prefix: Префикс для callback данных
        :param max_length: Максимальная длина callback данных (Telegram лимит 64 байта)
        :return: Безопасная строка для callback_data
        """
        # Приоритет идентификаторов: external_id > url_id > title_hash
        if self.external_id and self.source:
            # Очищаем external_id от специальных символов
            clean_id = self._clean_callback_string(self.external_id)
            data = f"{prefix}:{self.source}:{clean_id}"
        elif self.url:
            # Извлекаем ID из URL
            url_parts = self.url.rstrip('/').split('/')
            url_id = url_parts[-1] if url_parts[-1] else (url_parts[-2] if len(url_parts) > 1 else "unknown")
            clean_id = self._clean_callback_string(url_id)
            data = f"{prefix}:url:{clean_id}"
        else:
            # Используем хеш от заголовка как последний вариант
            title_hash = hashlib.sha256(self.title.encode()).hexdigest()
            data = f"{prefix}:hash:{title_hash}"
        
        # Обрезаем до максимальной длины, оставляя место для префикса
        if len(data) > max_length:
            # Вычисляем доступную длину для ID
            prefix_part = data.split(':')[:-1]
            prefix_length = len(':'.join(prefix_part)) + 1  # +1 для последнего ':'
            available_length = max_length - prefix_length
            
            if available_length > 0:
                last_part = data.split(':')[-1]
                truncated_part = last_part[:available_length]
                data = ':'.join(prefix_part) + ':' + truncated_part
            else:
                # Если даже префикс слишком длинный, используем простой хеш
                simple_hash = abs(hash(self.title or self.url or "unknown")) % 100000
                data = f"{prefix[:10]}:{simple_hash}"
        
        return data
    
    def _clean_callback_string(self, text: str) -> str:
        """
        Очищает строку от символов, которые могут вызвать проблемы в callback_data.
        
        :param text: Исходная строка
        :return: Очищенная строка
        """
        if not text:
            return "unknown"
        
        # Удаляем или заменяем проблемные символы
        # Telegram callback_data не должен содержать некоторые специальные символы
        cleaned = text.replace(' ', '_').replace('\n', '').replace('\r', '')
        cleaned = ''.join(char for char in cleaned if ord(char) < 128)  # Только ASCII
        
        # Удаляем последовательные подчеркивания
        while '__' in cleaned:
            cleaned = cleaned.replace('__', '_')
        
        # Убираем подчеркивания в начале и конце
        cleaned = cleaned.strip('_')
        
        return cleaned or "unknown"
    
    def get_display_title(self, max_length: int = 100) -> str:
        """
        Возвращает заголовок статьи, обрезанный до указанной длины.
        
        :param max_length: Максимальная длина заголовка
        :return: Обрезанный заголовок
        """
        if not self.title:
            return "Без названия"
        
        if len(self.title) <= max_length:
            return self.title
        
        return self.title[:max_length-3] + "..."
    
    def get_authors_string(self, max_authors: int = 3, max_length: int = 100) -> str:
        """
        Возвращает строку с авторами, ограниченную по количеству и длине.
        
        :param max_authors: Максимальное количество авторов для отображения
        :param max_length: Максимальная длина строки с авторами
        :return: Строка с авторами
        """
        if not self.authors:
            return "Авторы не указаны"
        
        authors_to_show = self.authors[:max_authors]
        authors_str = ", ".join(authors_to_show)
        
        if len(self.authors) > max_authors:
            authors_str += f" и ещё {len(self.authors) - max_authors}"
        
        if len(authors_str) > max_length:
            authors_str = authors_str[:max_length-3] + "..."
        
        return authors_str 
    
    def __str__(self):
        return f"Article(title={self.title}, authors={self.authors}, doi={self.doi}, url={self.url})"
    
class PaperSearcher(ABC):
    """
    Абстрактный класс для поиска научных статей.
    """
    @abstractmethod
    async def search_papers(self, query: str, limit: int = 10, filters: Optional[Dict[str, Any]] = None) -> List[Paper]:
        """
        Поиск статей по запросу.

        :param query: Запрос для поиска.
        :param limit: Максимальное количество результатов для возврата.
        :param filters: Фильтры для поиска (year, author, journal и т.д.)
        :return: Список объектов Paper.
        """
        pass
    
    @abstractmethod
    async def get_paper_by_url(self, url: str) -> Paper:
        """
        Получение подробной информации о статье по её URL.
        """
        pass

    @abstractmethod
    async def get_full_text_by_id(self, paper_id: str) -> str:
        """
        Получение полного текста статьи по её ID.
        """
        pass