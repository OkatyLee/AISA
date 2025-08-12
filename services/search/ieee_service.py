from datetime import datetime
import httpx
from config import load_config
from utils import setup_logger
from services.utils.paper import Paper, PaperSearcher
from config.constants import IEEE_API_BASE_URL, API_TIMEOUT_SECONDS
from typing import Optional, Dict, Any

logger = setup_logger(
    name="ieee_service_logger",
    log_file='logs/ieee_service.log',
    level='INFO'
)

class IEEESearcher(PaperSearcher):
    
    def __init__(self):
        config = load_config()
        self.api_key = config.IEEE_API_KEY
        if not self.api_key:
            logger.warning("IEEE_API_KEY is not set")
            raise ValueError("IEEE_API_KEY is required but not set in the configuration")
        self.client = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=IEEE_API_BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(API_TIMEOUT_SECONDS, connect=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.client:
            await self.client.aclose()
    
    async def search_papers(self, query: str, limit: int = 10, filters: Optional[Dict[str, Any]] = None) -> list[Paper]:
        """
        Поиск статей по запросу в IEEE API.
        
        :param query: Запрос для поиска.
        :param limit: Максимальное количество результатов для возврата.
        :param filters: Фильтры для поиска (year, author и т.д.)
        :return: Список объектов Paper.
        """
        # Строим поисковый запрос с учетом фильтров
        enhanced_query = self._build_enhanced_query(query, filters)
        
        params = {
            "querytext": enhanced_query,
            "max_records": min(limit, 200),
            "start_record": 1
        }
        
        # Добавляем параметры фильтрации через API, если поддерживается
        if filters:
            if 'year' in filters and filters['year']:
                params["publication_year"] = str(filters['year'])

        response = await self._make_request(params)
        data = response.json()
        
        papers = []
        if 'articles' in data:
            for item in data['articles']:
                paper = self._parse_ieee_article(item)
                if paper:
                    papers.append(paper)
        
        # Применяем дополнительную фильтрацию
        if filters:
            papers = self._apply_post_filters(papers, filters)
                            
        return papers
    
    async def get_paper_by_url(self, url: str) -> Paper:
        """
        Получение статьи по URL из IEEE API.
        
        :param url: URL статьи.
        :return: Объект Paper.
        """
        if not url.startswith("https://ieeexplore.ieee.org/document/"):
            raise ValueError("Invalid IEEE document URL")
        
        paper_id = url.split("/")[-1]
        params = {
            "article_number": paper_id,
            "max_records": 1
        }
        
        response = await self._make_request(params)
        data = response.json()
        
        if 'articles' in data and len(data['articles']) > 0:
            return self._parse_ieee_article(data['articles'][0])
        
        logger.warning(f"Article with ID {paper_id} not found in IEEE API")
        return None
    
    async def _make_request(self, params: dict) -> httpx.Response:
        """
        Выполнение запроса к IEEE API.
        
        :param params: Параметры запроса.
        :return: Ответ от API.
        """
        params['apikey'] = self.api_key  
        params['format'] = 'json'
        
        try:
            response = await self.client.get("", params=params)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка при запросе к IEEE API: {e.response.status_code} - {e.response.text}")
            raise
    
    def _parse_ieee_article(self, item: dict) -> Paper:
        """
        Парсинг статьи из ответа IEEE API.
        
        :param item: Словарь с данными статьи.
        :return: Объект Paper.
        """
        try:
            paper = Paper()
            paper.title = item.get('title', '')
            # IEEE ID 
            paper.external_id = str(item.get('article_number', ''))
            paper.source = 'ieee'
            if 'authors' in item:
                if isinstance(item['authors'], dict):
                    authors_data = item['authors'].get('authors', [])
                    for author in authors_data:
                        if isinstance(author, dict):
                            full_name = author.get('full_name', '')
                            if full_name:
                                paper.authors.append(full_name)
            paper.abstract = item.get('abstract', '')
            paper.doi = item.get('doi', '')
            paper.publication_date = datetime.fromisoformat(item.get('publication_year', ''))
            paper.journal = item.get('publication_title', '')
            paper.keywords = item.get('keywords', [])
            if paper.external_id:
                paper.url = f"https://ieeexplore.ieee.org/document/{paper.external_id}"
            if 'index_terms' in item:
                index_terms = item['index_terms']
                if isinstance(index_terms, dict):
                    # Авторские ключевые слова
                    author_terms = index_terms.get('author_terms', {})
                    if isinstance(author_terms, dict) and 'terms' in author_terms:
                        paper.keywords.extend(author_terms['terms'])
                    
                    # IEEE термины
                    ieee_terms = index_terms.get('ieee_terms', {})
                    if isinstance(ieee_terms, dict) and 'terms' in ieee_terms:
                        paper.keywords.extend(ieee_terms['terms'])
            return paper
        except Exception as e:
            logger.error(f"Ошибка при парсинге статьи IEEE: {e}")
            return None
    
    def _build_enhanced_query(self, query: str, filters: Optional[Dict[str, Any]] = None) -> str:
        """
        Строит улучшенный запрос для IEEE API с учетом фильтров
        
        Args:
            query: Базовый поисковый запрос
            filters: Фильтры поиска
            
        Returns:
            Улучшенный поисковый запрос
        """
        query_parts = [query]
        
        if filters:
            # Фильтр по автору - добавляем в запрос
            if 'author' in filters and filters['author']:
                author = filters['author']
                query_parts.append(f'("{author}" in au)')
        
        return ' AND '.join(query_parts)
    
    async def get_full_text_by_id(self, paper_id):
        return await super().get_full_text_by_id(paper_id)
    
    def _apply_post_filters(self, papers: list[Paper], filters: Dict[str, Any]) -> list[Paper]:
        """
        Применяет дополнительные фильтры к результатам поиска
        
        Args:
            papers: Список статей для фильтрации
            filters: Словарь с фильтрами
            
        Returns:
            Отфильтрованный список статей
        """
        filtered_papers = []
        
        for paper in papers:
            # Фильтр по автору (дополнительная проверка)
            if 'author' in filters and filters['author']:
                author_filter = filters['author'].lower()
                paper_authors = [author.lower() for author in paper.authors]
                if not any(author_filter in author for author in paper_authors):
                    continue
            
            # Фильтр по году (если не был применен через API)
            if 'year' in filters and filters['year']:
                year_filter = str(filters['year'])
                if paper.publication_date:
                    paper_year = str(paper.publication_date)
                    if paper_year != year_filter:
                        continue
            
            filtered_papers.append(paper)
        
        return filtered_papers