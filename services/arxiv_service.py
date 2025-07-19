import httpx
from config.config import load_config
from config.constants import ARXIV_API_BASE_URL, ARXIV_NAMESPACES, API_TIMEOUT_SECONDS
from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET
from datetime import datetime
from utils import setup_logger
from utils.metrics import metrics
import logging
from aiogram.utils.markdown import hbold, hitalic, hlink
from urllib.parse import urlparse
import re

logger = setup_logger(name="arxiv_service_logger", log_file="logs/arxiv_service.log", level=logging.INFO)

class ArxivSearcher:
    """
    Класс для работы с ArXiv API
    
    Обеспечивает поиск научных статей, кэширование результатов
    и обработку ошибок API
    """

    def __init__(self):
        self.session = None
        self.config = load_config()
        self.MAX_RESULTS = self.config.MAX_RESULTS
        self._cache = {}  # Простой кэш для повторных запросов

    async def __aenter__(self):
        self.session = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True
        )
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.session:
            await self.session.aclose()

    async def search_papers(self, query: str) -> List[Dict[str, str]]:
        """
        Поиск статей в ArXiv API с кэшированием
        
        Args:
            query: Поисковый запрос
            
        Returns:
            Список словарей с информацией о статьях
        """
        if not self.session:
            raise ValueError("ArxivSearcher is not initialized")
            
        # Проверяем кэш
        cache_key = f"search_{hash(query)}_{self.MAX_RESULTS}"
        if cache_key in self._cache:
            logger.info(f"Возвращаем результат из кэша для запроса: {query}")
            metrics.record_operation("arxiv_search_cache_hit", 0, None, True)
            return self._cache[cache_key]
        
        # Записываем начало операции поиска
        search_start_time = datetime.now()
        
        try:
            # Улучшенные параметры поиска
            url = ARXIV_API_BASE_URL
            params = {
                'search_query': self._build_search_query(query),
                'start': 0,
                'sortBy': 'relevance',
                'sortOrder': 'descending',
                "max_results": self.MAX_RESULTS 
            }

            logger.info(f"Выполняем поиск ArXiv с запросом: {params['search_query']}")
            response = await self.session.get(url, params=params)
            response.raise_for_status()

            papers = self._parse_arxiv_response(response.text)
            
            # Сохраняем в кэш
            self._cache[cache_key] = papers
            
            # Записываем успешную операцию
            search_duration = (datetime.now() - search_start_time).total_seconds()
            metrics.record_operation("arxiv_search_success", 0, search_duration, True)
            logger.info(f"Найдено {len(papers)} статей для запроса: {query}")
            
            return papers
            
        except httpx.HTTPStatusError as e:
            search_duration = (datetime.now() - search_start_time).total_seconds()
            metrics.record_operation("arxiv_search_http_error", 0, search_duration, False)
            logger.error(f"HTTP ошибка: {e.response.status_code} - {e.response.text}")
            return []
        except httpx.TimeoutException as e:
            search_duration = (datetime.now() - search_start_time).total_seconds()
            metrics.record_operation("arxiv_search_timeout", 0, search_duration, False)
            logger.error(f"Время ожидания ответа истекло: {e}")
            return []
        except httpx.ConnectError as e:
            search_duration = (datetime.now() - search_start_time).total_seconds()
            metrics.record_operation("arxiv_search_connection_error", 0, search_duration, False)
            logger.error(f"Ошибка соединения: {e}")
            return []
        except Exception as e:
            search_duration = (datetime.now() - search_start_time).total_seconds()
            metrics.record_operation("arxiv_search_unknown_error", 0, search_duration, False)
            logger.error(f"Неизвестная ошибка: {e}")
            return []
    
    def _build_search_query(self, query: str) -> str:
        """
        Создает оптимизированный поисковый запрос для ArXiv API
        
        Args:
            query: Исходный запрос пользователя
            
        Returns:
            Оптимизированный запрос для ArXiv API
        """
        # Удаляем специальные символы и лишние пробелы
        clean_query = re.sub(r'[^\w\s\-]', ' ', query).strip()
        clean_query = re.sub(r'\s+', ' ', clean_query)
        
        # Если запрос слишком короткий, ищем во всех полях
        if len(clean_query.split()) <= 2:
            return f'all:"{clean_query}"'
        
        # Для длинных запросов ищем в заголовке и аннотации
        return f'ti:"{clean_query}" OR abs:"{clean_query}"'

    def _parse_arxiv_response(self, response_text: str) -> List[Dict[str, str]]:
        """Парсинг ответа ArXiv API"""
        try:
            papers = []
            root = ET.fromstring(response_text)

            namespaces = ARXIV_NAMESPACES
            
            entries = root.findall('atom:entry', namespaces)
            
            for entry in entries:
                title = entry.find('atom:title', namespaces)
                title_text = title.text.strip().replace('\n', ' ')
                
                summary = entry.find('atom:summary', namespaces)
                if summary is not None:
                    summary_text = summary.text.strip().replace('\n', ' ')
                    
                    if len(summary_text) > 200:
                        summary_text = summary_text[:200] + "..."
                else:
                    summary_text = "Аннотация не найдена"
                    
                published = entry.find('atom:published', namespaces)
                if published is not None:
                    pub_date = datetime.fromisoformat(published.text.replace('Z', '+00:00'))
                    formatted_date = pub_date.strftime('%Y-%m-%d')
                else:
                    formatted_date = "Дата не указана"
                    
                url = entry.find('atom:id', namespaces)
                url_text = url.text.strip() if url is not None else ""
                
                authors = entry.findall('atom:author', namespaces)
                
                author_names = []
                for author in authors:
                    name = author.find('atom:name', namespaces)
                    if name is not None:
                        author_names.append(name.text.strip())
                arxiv_id = self._extract_arxiv_id(url_text)
                
                categories = []
                for category in entry.findall('atom:category', namespaces):
                    term = category.get('term')
                    if term:
                        categories.append(term)
                    
                    paper = {
                        'title': title_text,
                        'authors': author_names,
                        'url': url_text,
                        'published_date': formatted_date,
                        'abstract': summary_text,
                        'categories': categories[:3],
                        'arxiv_id': arxiv_id,
                    }
                papers.append(paper)
            return papers
        except ET.ParseError as e:
            logger.error(f"Ошибка в парсинге XML: {e}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка: {e}")
            return []
        
    async def get_paper_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            if not url or not isinstance(url, str):
                logger.error("Некорректный URL")
                return None
            
            url = url.strip()
            if not url:
                logger.error("Пустой URL")
                return None
            
            arxiv_id = self._extract_arxiv_id(url)
            if not arxiv_id:
                logger.error(f"Не удалось извлечь Arxiv ID из URL: {url}")
                return None

            params = {
                'search_query': f'id:{arxiv_id}',
                'start': 0,
                'max_results': 1
            }
            
            try:
                response = await self.session.get(
                    ARXIV_API_BASE_URL,
                    params=params,
                    timeout=API_TIMEOUT_SECONDS
                )
                response.raise_for_status()
                
            except httpx.TimeoutException:
                logger.error(f"Таймаут при запросе к ArXiv API для {arxiv_id}")
                return None
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP ошибка {e.response.status_code} для {arxiv_id}")
                return None
            except httpx.RequestError as e:
                logger.error(f"Ошибка сети при запросе {arxiv_id}: {e}")
                return None
            
            if not response.content:
                logger.error(f"Пустой ответ от ArXiv API для {arxiv_id}")
                return None
            
            paper_data = self._parse_arxiv_response(response.text)[0]
            if not paper_data:
                logger.error(f"Не удалось распарсить ответ для {arxiv_id}")
                return None

            return paper_data
            
        except Exception as e:
            logger.error(f"Неожиданная ошибка при получении статьи: {e}")
            return None
    
    def _extract_arxiv_id(self, url: str) -> Optional[str]:
        """Извлечение ArXiv ID из URL"""
        try:
            parsed = urlparse(url)
            
            patterns = [
                r'/abs/(\d{4}\.\d{4,5})(v\d+)?',
                r'/pdf/(\d{4}\.\d{4,5})(v\d+)?\.pdf',
                r'/abs/([a-z-]+/\d{7})(v\d+)?',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, parsed.path)
                if match:
                    return match.group(1)
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка извлечения ArXiv ID: {e}")
            return None

def format_paper_message(paper: Dict[str, Any], index: int) -> str:
    """Форматирование информации о статье для вывода"""
    title = hbold(f"{index}. {paper['title']}")
    
    authors_text = ', '.join(paper['authors'][:3])
    if len(paper['authors']) > 3:
        authors_text += f" и еще {len(paper['authors']) - 3} автора"
    authors = hitalic(authors_text)

    date = f'Опубликовано: {paper["published_date"]}' if paper['published_date'] else 'Дата публикации не указана'
    categories = ''
    if paper['categories']:
        categories = ', '.join(paper['categories'])
    
    summary = f"📄 {paper['abstract']}"
    
    # Ссылка
    url = hlink("🔗 Читать статью", paper['url'])
    
    # Собираем всё вместе
    parts = [title, authors, date]
    if categories:
        parts.append(categories)
    parts.extend([summary, url])
    return '\n'.join(parts)