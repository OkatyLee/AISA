import httpx
from config.config import load_config
from config.constants import ARXIV_API_BASE_URL, ARXIV_NAMESPACES, API_TIMEOUT_SECONDS
from typing import List, Optional, Dict, Any
import xml.etree.ElementTree as ET
from datetime import datetime
from utils import setup_logger
from utils.metrics import metrics
import logging
from urllib.parse import urlparse
import re
from services.utils.paper import Paper, PaperSearcher
import fitz

logger = setup_logger(name="arxiv_service_logger", log_file="logs/arxiv_service.log", level=logging.INFO)

class ArxivSearcher(PaperSearcher):
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

    async def search_papers(self, query: str, limit: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Paper]:
        """
        Поиск статей в ArXiv API с кэшированием
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов (по умолчанию 5)
            filters: Фильтры поиска (year, author и т.д.)
            
        Returns:
            Список словарей с информацией о статьях
        """
        if not self.session:
            raise ValueError("ArxivSearcher is not initialized")
            
        # Создаем ключ кэша с учетом фильтров
        cache_key = f"search_{hash(query)}_{limit}_{hash(str(filters))}"
        if cache_key in self._cache:
            logger.info(f"Возвращаем результат из кэша для запроса: {query}")
            metrics.record_operation("arxiv_search_cache_hit", 0, None, True)
            return self._cache[cache_key]
        
        # Записываем начало операции поиска
        search_start_time = datetime.now()
        
        try:
            url = ARXIV_API_BASE_URL
            # Строим запрос с учетом фильтров
            search_query = self._build_search_query(query, filters)
            params = {
                'search_query': search_query,
                'start': 0,
                'sortBy': 'relevance',
                'sortOrder': 'descending',
                "max_results": limit
            }

            logger.info(f"Выполняем поиск ArXiv с запросом: {params['search_query']}")
            response = await self.session.get(url, params=params)
            response.raise_for_status()

            papers = self._parse_arxiv_response(response.text)
            
            # Применяем дополнительную фильтрацию
            if filters:
                papers = self._apply_post_filters(papers, filters)
            
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
    
    def _build_search_query(self, query: str, filters: Optional[Dict[str, Any]] = None) -> str:
        """
        Создает оптимизированный поисковый запрос для ArXiv API с учетом фильтров
        
        Args:
            query: Исходный запрос пользователя
            filters: Фильтры поиска (year, author и т.д.)
            
        Returns:
            Оптимизированный запрос для ArXiv API
        """
        # Удаляем специальные символы и лишние пробелы
        clean_query = re.sub(r'[^\w\s\-]', ' ', query).strip()
        clean_query = re.sub(r'\s+', ' ', clean_query)
        
        # Базовый запрос
        if len(clean_query.split()) <= 2:
            base_query = f'all:"{clean_query}"'
        else:
            base_query = f'ti:"{clean_query}" OR abs:"{clean_query}"'
        
        # Добавляем фильтры
        query_parts = [base_query]
        
        if filters:
            # Фильтр по автору
            if 'author' in filters and filters['author']:
                author = filters['author']
                query_parts.append(f'au:"{author}"')
            
            # Фильтр по году 
            if 'year' in filters and filters['year']:
                year = str(filters['year'])
                # ArXiv поддерживает фильтрацию по дате публикации
                query_parts.append(f'submittedDate:[{year}0101 TO {year}1231]')
            
            # Фильтр по журналу/категории
            if 'journal' in filters and filters['journal']:
                journal = filters['journal']
                query_parts.append(f'cat:"{journal}"')
        
        # Объединяем все части через AND
        return ' AND '.join(query_parts)
    
    def _apply_post_filters(self, papers: List[Paper], filters: Dict[str, Any]) -> List[Paper]:
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
            
            # Фильтр по году
            if 'year' in filters and filters['year']:
                year_filter = str(filters['year'])
                if paper.publication_date:
                    try:
                        # Пробуем извлечь год из даты публикации
                        if isinstance(paper.publication_date, str):
                            paper_year = paper.publication_date[:4] if len(paper.publication_date) >= 4 else None
                        else:
                            paper_year = str(paper.publication_date.year) if hasattr(paper.publication_date, 'year') else None
                        
                        if paper_year != year_filter:
                            continue
                    except (ValueError, AttributeError):
                        # Если не можем извлечь год, пропускаем статью
                        continue
            
            filtered_papers.append(paper)
        
        return filtered_papers

    def _parse_arxiv_response(self, response_text: str, truncate_abstract: bool = True) -> List[Paper]:
        """Парсинг ответа ArXiv API"""
        try:
            papers = []
            root = ET.fromstring(response_text)

            namespaces = ARXIV_NAMESPACES
            
            entries = root.findall('atom:entry', namespaces)
            
            for entry in entries:
                
                paper = self._parse_arxiv_paper(entry, truncate_abstract)   
                papers.append(paper)
            return papers
        except ET.ParseError as e:
            logger.error(f"Ошибка в парсинге XML: {e}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка: {e}")
            return []
    
    def _parse_arxiv_paper(self, entry: ET.Element, truncate_abstract: bool = True) -> Paper:
        paper = Paper()
        namespaces = ARXIV_NAMESPACES
        title = entry.find('atom:title', namespaces)
        title_text = title.text.strip().replace('\n', ' ') if title is not None else ""
        paper.title = title_text
        summary = entry.find('atom:summary', namespaces)
        if summary is not None:
            summary_text = summary.text.strip().replace('\n', ' ')
            
            if len(summary_text) > 200 and truncate_abstract:
                summary_text = summary_text[:200] + "..."
        else:
            summary_text = "Аннотация не найдена"
        paper.abstract = summary_text
            
        published = entry.find('atom:published', namespaces)
        if published is not None:
            pub_date = datetime.fromisoformat(published.text.replace('Z', '+00:00'))
            formatted_date = pub_date.strftime('%Y-%m-%d')
        else:
            formatted_date = "Дата не указана"
        paper.publication_date = formatted_date
        url = entry.find('atom:id', namespaces)
        url_text = url.text.strip() if url is not None else ""
        paper.url = url_text
        authors = entry.findall('atom:author', namespaces)
        
        author_names = []
        for author in authors:
            name = author.find('atom:name', namespaces)
            if name is not None:
                author_names.append(name.text.strip())
        paper.authors = author_names
        arxiv_id = self._extract_arxiv_id(url_text)
        if arxiv_id:
            paper.external_id = arxiv_id
            paper.source = 'arxiv'
        
        categories = []
        for category in entry.findall('atom:category', namespaces):
            term = category.get('term')
            if term:
                categories.append(term)
        paper.keywords = categories
        if paper.keywords:
            paper.journal = f"arXiv:{paper.keywords[0]}"
        return paper

    async def get_paper_by_url(self, url: str, truncate_abstract: bool = True) -> Optional[Paper]:
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
            
            paper_data = self._parse_arxiv_response(response.text, truncate_abstract)[0]
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

    async def get_full_text_by_id(self, paper_id: str) -> str:
        '''
        Получение полного текста статьи по её ID.
        '''
        try:
            pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
            logger.info(f"Получаем полный текст статьи по url: {pdf_url}")
            
            response = await self.session.get(pdf_url, timeout=API_TIMEOUT_SECONDS)
            response.raise_for_status()
            
            pdf_bytes = response.content
            
            # Диагностика загруженных данных
            logger.info(f"HTTP статус: {response.status_code}")
            logger.info(f"Content-Type: {response.headers.get('content-type', 'не указан')}")
            logger.info(f"Размер загруженных данных: {len(pdf_bytes)} байт")
            
            # Проверяем размер данных
            if len(pdf_bytes) < 1000:
                logger.error(f"Подозрительно маленький размер файла: {len(pdf_bytes)} байт")
                logger.error(f"Содержимое: {pdf_bytes}")
                return ""
            
            # Проверяем Content-Type
            content_type = response.headers.get('content-type', '').lower()
            if 'application/pdf' not in content_type and 'application/octet-stream' not in content_type:
                logger.warning(f"Неожиданный Content-Type: {content_type}")
                
                if 'text/html' in content_type:
                    # Получили HTML вместо PDF
                    html_content = pdf_bytes.decode('utf-8', errors='ignore')[:1000]
                    logger.error(f"Получен HTML вместо PDF: {html_content}")
                    return ""
            
            # Проверяем PDF заголовок
            if not pdf_bytes.startswith(b'%PDF'):
                logger.error("Данные не являются валидным PDF файлом")
                logger.error(f"Первые 50 байт: {pdf_bytes[:50]}")
                
                # Пробуем декодировать как текст для диагностики
                try:
                    text_preview = pdf_bytes[:500].decode('utf-8', errors='ignore')
                    logger.error(f"Содержимое как текст: {text_preview}")
                    
                    # Проверяем на типичные ошибки arXiv
                    if '<html' in text_preview.lower():
                        logger.error("Получена HTML страница")
                    elif 'not found' in text_preview.lower():
                        logger.error("Статья не найдена")
                    elif 'rate limit' in text_preview.lower() or 'too many' in text_preview.lower():
                        logger.error("Превышен лимит запросов")
                        
                except UnicodeDecodeError:
                    logger.error("Данные не являются текстом")
                
                return ""
            
            # Проверяем окончание PDF
            if not pdf_bytes.rstrip().endswith(b'%%EOF'):
                logger.warning("PDF файл может быть неполным (нет %%EOF в конце)")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка загрузки PDF. Статус: {e.response.status_code} для ID: {paper_id}")
            
            # Дополнительная диагностика для разных статусов
            if e.response.status_code == 403:
                logger.error("Доступ запрещен - возможно превышен лимит запросов к arXiv")
            elif e.response.status_code == 404:
                logger.error(f"Статья с ID {paper_id} не найдена")
            elif e.response.status_code == 429:
                logger.error("Слишком много запросов - нужно добавить задержку")
            
            raise Exception(f"Ошибка загрузки PDF. Статус: {e.response.status_code} для ID: {paper_id}")
            
        except httpx.RequestError as e:
            logger.error(f"Ошибка сети при запросе к {e.request.url!r}: {e}")
            raise Exception(f"Ошибка сети при запросе к {e.request.url!r}.")
        
        logger.info(f"PDF для статьи {paper_id} успешно загружен и проверен")
        
        # Извлекаем текст из PDF
        full_text = []
        try:
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            # Проверяем количество страниц
            page_count = pdf_document.page_count
            logger.info(f"PDF содержит {page_count} страниц")
            
            if page_count == 0:
                logger.warning("PDF документ не содержит страниц")
                pdf_document.close()
                return ""
            
            # Извлекаем текст постранично с обработкой ошибок
            for page_num, page in enumerate(pdf_document):
                try:
                    page_text = page.get_text()
                    if page_text.strip():  # Добавляем только непустые страницы
                        full_text.append(page_text)
                    else:
                        logger.debug(f"Страница {page_num + 1} пустая")
                except Exception as page_error:
                    logger.error(f"Ошибка при извлечении текста со страницы {page_num + 1}: {page_error}")
                    continue
            
            pdf_document.close()
            
            if not full_text:
                logger.warning(f"Не удалось извлечь текст ни с одной страницы из {page_count} страниц")
                return ""
            
            result = "\n".join(full_text)
            logger.info(f"Успешно извлечен текст из {len(full_text)} страниц, общая длина: {len(result)} символов")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении текста из PDF: {e}")
            logger.error(f"Тип ошибки: {type(e).__name__}")
            
            # Дополнительная диагностика
            try:
                # Пробуем открыть как поток еще раз для диагностики
                import io
                pdf_stream = io.BytesIO(pdf_bytes)
                test_doc = fitz.open(stream=pdf_stream, filetype="pdf")
                logger.info(f"Альтернативная проверка: документ открывается, страниц: {test_doc.page_count}")
                test_doc.close()
            except Exception as alt_error:
                logger.error(f"Альтернативная проверка тоже не удалась: {alt_error}")
            
            return ""
