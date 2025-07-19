
from abc import ABC, abstractmethod
from typing import List


class Paper:
    """
    Класс, представляющий научную статью.
    """
    def __init__(self):
        self.title = ""
        self.authors = []
        self.abstract = ""
        self.doi = ""
        self.publication_date = ""
        self.journal = ""
        self.keywords = []
        self.url = ""
        
        self.external_id = ''
        self.source = ''
        
        self.source_metadata = {}
        
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
    
    def __str__(self):
        return f"Article(title={self.title}, authors={self.authors}, doi={self.doi}, url={self.url})"
    
class PaperSearcher(ABC):
    """
    Абстрактный класс для поиска научных статей.
    """
    @abstractmethod
    async def search_papers(self, query: str, limit: int = 10) -> List[Paper]:
        """
        Поиск статей по запросу.

        :param query: Запрос для поиска.
        :param limit: Максимальное количество результатов для возврата.
        :return: Список объектов Article.
        """
        pass
    
    @abstractmethod
    async def get_paper_by_url(self, url: str) -> Paper:
        """
        Получение подробной информации о статье по её URL.
        """
        pass