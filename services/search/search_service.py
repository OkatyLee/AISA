import asyncio
from datetime import datetime
from operator import call
import re
from typing import List, Dict, Any, Optional

from dateutil.parser import parse
from numpy import full
from regex import W
from sympy import N

from services.search.semantic_scholar_service import SemanticScholarSearcher
from services.utils import paper
from services.utils.paper import Paper, PaperSearcher
from services.search import ArxivSearcher
from services.search import IEEESearcher
from services.search import NCBISearcher
from utils import setup_logger
from typing import Tuple

logger = setup_logger(
    name="search_service_logger",
    log_file='logs/search_service.log',
    level='DEBUG'
)


class SearchResult:
    """Результат поиска от одного сервиса."""
    
    def __init__(self, source: str, papers: List[Paper], error: Optional[str] = None):
        self.source = source
        self.papers = papers
        self.error = error
        self.success = error is None


class SearchService:
    """
    Центральный сервис для поиска научных статей через различные API.
    
    Поддерживает асинхронный поиск через несколько источников одновременно,
    агрегацию результатов и обработку ошибок.
    """

    def __init__(self, services: Optional[Dict[str, PaperSearcher]] = None):
        """
        Инициализация SearchService.
        
        Args:
            services: Словарь с сервисами поиска. Если не указан, 
                     используются все доступные сервисы по умолчанию.
        """
        if services is None:
            self._services = {
                'semantic_scholar': SemanticScholarSearcher(),
                'arxiv': ArxivSearcher(),
                'ieee': IEEESearcher(),
                'ncbi': NCBISearcher()
            }
        else:
            self._services = services
        
        logger.info(f"Инициализирован SearchService с сервисами: {list(self._services.keys())}")

    def __enter__(self):
        """Контекстный менеджер для использования SearchService."""
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        """Закрытие сервисов при выходе из контекстного менеджера."""
        for service in self._services.values():
            if hasattr(service, 'close'):
                service.close()
        logger.info("Закрыты все сервисы в SearchService")

    async def __aenter__(self):
        """Асинхронный контекстный менеджер для использования SearchService."""
        logger.info("Инициализация асинхронного контекстного менеджера SearchService")
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        """Закрытие сервисов при выходе из асинхронного контекстного менеджера."""
        for service_name, service in self._services.items():
            try:
                if hasattr(service, '__aexit__'):
                    await service.__aexit__(exc_type, exc_value, traceback)
                elif hasattr(service, 'close'):
                    if asyncio.iscoroutinefunction(service.close):
                        await service.close()
                    else:
                        service.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии сервиса {service_name}: {e}")
        logger.info("Закрыты все сервисы в асинхронном SearchService")

    def add_service(self, name: str, service: PaperSearcher) -> None:
        """
        Добавить новый поисковый сервис.
        
        Args:
            name: Название сервиса
            service: Экземпляр класса, наследующего PaperSearcher
        """
        if not isinstance(service, PaperSearcher):
            raise ValueError(f"Service must inherit from PaperSearcher")
            
        self._services[name] = service
        logger.info(f"Добавлен новый сервис: {name}")

    def remove_service(self, name: str) -> None:
        """
        Удалить поисковый сервис.
        
        Args:
            name: Название сервиса для удаления
        """
        if name in self._services:
            del self._services[name]
            logger.info(f"Удален сервис: {name}")
        else:
            logger.warning(f"Сервис {name} не найден для удаления")

    def get_available_services(self) -> List[str]:
        """Получить список доступных сервисов."""
        return list(self._services.keys())

    async def search_papers(
        self,
        query: str,
        limit: int = 10,
        services: Optional[List[str]] = None,
        concurrent: bool = True,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, SearchResult]:
        """
        Поиск статей через выбранные сервисы.
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов на сервис
            services: Список сервисов для использования. Если None, используются все
            concurrent: Выполнять поиск параллельно
            filters: Фильтры поиска (year, author и т.д.)
            
        Returns:
            Словарь с результатами поиска по каждому сервису
        """
        if services is None:
            services = list(self._services.keys())
        
        # Фильтруем только доступные сервисы
        available_services = {name: service for name, service in self._services.items() 
                            if name in services}
        
        if not available_services:
            logger.warning(f"Нет доступных сервисов для поиска: {services}")
            return {}

        logger.info(f"Начинаем поиск по запросу '{query}' через сервисы: {list(available_services.keys())}")

        if concurrent:
            return await self._search_concurrent(query, limit, available_services, filters)
        else:
            return await self._search_sequential(query, limit, available_services, filters)

    async def _search_concurrent(
        self,
        query: str,
        limit: int,
        services: Dict[str, PaperSearcher],
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, SearchResult]:
        """Параллельный поиск через все сервисы."""
        tasks = []
        
        for name, service in services.items():
            task = asyncio.create_task(
                self._search_single_service(name, service, query, limit, filters),
                name=f"search_{name}"
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        search_results = {}
        for i, (name, _) in enumerate(services.items()):
            result = results[i]
            if isinstance(result, Exception):
                logger.error(f"Ошибка при поиске в {name}: {result}")
                search_results[name] = SearchResult(name, [], str(result))
            else:
                search_results[name] = result
        
        return search_results

    async def _search_sequential(
        self,
        query: str,
        limit: int,
        services: Dict[str, PaperSearcher],
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, SearchResult]:
        """Последовательный поиск через сервисы."""
        results = {}
        
        for name, service in services.items():
            try:
                result = await self._search_single_service(name, service, query, limit, filters)
                results[name] = result
            except Exception as e:
                logger.error(f"Ошибка при поиске в {name}: {e}")
                results[name] = SearchResult(name, [], str(e))
        
        return results

    async def _search_single_service(
        self,
        name: str,
        service: PaperSearcher,
        query: str,
        limit: int,
        filters: Optional[Dict[str, Any]] = None
    ) -> SearchResult:
        """Поиск через один сервис."""
        try:
            async with service:
                papers = await service.search_papers(query, limit, filters)
                logger.info(f"Сервис {name}: найдено {len(papers)} статей")
                return SearchResult(name, papers)
        except Exception as e:
            logger.error(f"Ошибка в сервисе {name}: {e}")
            return SearchResult(name, [], str(e))

    async def get_paper_by_url(self, url: str) -> Optional[Paper]:
        """
        Получить статью по URL, автоматически определив подходящий сервис.
        
        Args:
            url: URL статьи
            
        Returns:
            Paper объект или None, если статья не найдена
        """
        service_name = self._detect_service_by_url(url)
        
        if not service_name or service_name not in self._services:
            logger.warning(f"Не удалось определить сервис для URL: {url}")
            return None
        
        service = self._services[service_name]
        
        try:
            async with service:
                paper = await service.get_paper_by_url(url)
                if paper:
                    logger.info(f"Статья найдена через сервис {service_name}")
                else:
                    logger.warning(f"Статья не найдена по URL: {url}")
                return paper
        except Exception as e:
            logger.error(f"Ошибка при получении статьи по URL {url}: {e}")
            return None

    def _detect_service_by_url(self, url: str) -> Optional[str]:
        """Определить сервис по URL статьи."""
        url_lower = url.lower()
        
        if 'arxiv.org' in url_lower:
            return 'arxiv'
        elif 'ieeexplore.ieee.org' in url_lower:
            return 'ieee'
        elif 'pubmed.ncbi.nlm.nih.gov' in url_lower or 'ncbi.nlm.nih.gov' in url_lower:
            return 'ncbi'
        elif 'semanticscholar.org' in url_lower:
            return 'semantic_scholar'

        return None

    def aggregate_results(
        self,
        search_results: Dict[str, SearchResult],
        query: str, 
        remove_duplicates: bool = True,
        sort_by: str = 'relevance'
    ) -> List[Paper]:
        """
        Агрегировать результаты поиска от всех сервисов.
        
        Args:
            search_results: Результаты поиска от всех сервисов
            remove_duplicates: Удалять дубликаты статей
            sort_by: Критерий сортировки ('relevance', 'date', 'title')
            
        Returns:
            Объединенный и отсортированный список статей
        """
        all_papers = []
        
        # Собираем все статьи
        for service_name, result in search_results.items():
            if result.success:
                all_papers.extend(result.papers)
                logger.info(f"Добавлено {len(result.papers)} статей от сервиса {service_name}")
            else:
                logger.warning(f"Пропуска   ем результаты от {service_name} из-за ошибки: {result.error}")
        
        # Удаляем дубликаты
        if remove_duplicates:
            all_papers = self._remove_duplicates(all_papers)
            logger.info(f"После удаления дубликатов осталось {len(all_papers)} статей")
        
        # Сортируем
        all_papers = self._sort_papers(all_papers, query, sort_by)

        return all_papers

    def _remove_duplicates(self, papers: List[Paper]) -> List[Paper]:
        """Удалить дубликаты статей на основе DOI, URL или названия."""
        seen = set()
        unique_papers = []
        
        for paper in papers:
            # Создаем ключ для идентификации дубликатов
            key = None
            
            # Приоритет: DOI > URL > нормализованное название
            if paper.external_id:
                key = ('external_id', paper.external_id.lower())
            elif paper.url:
                key = ('url', paper.url.lower())
            elif paper.title:
                # Нормализуем название для сравнения
                normalized_title = ''.join(paper.title.lower().split())
                key = ('title', normalized_title)
            
            if key and key not in seen:
                seen.add(key)
                unique_papers.append(paper)
        
        return unique_papers

    def _sort_papers(self, papers: List[Paper], query: str, sort_by: str) -> List[Paper]:
        """Сортировать статьи по заданному критерию."""
        query_words = set(query.lower().split())
        for paper in papers:
            score = 0
            
            source_bonus = {
                'semantic_scholar': 1,
                'arxiv': 0.8,
                'ncbi': 0.8,
                'ieee': 0.8
            }
            
            score += source_bonus.get(paper.source, 0.5)
            if paper.title:
                title_words = set(paper.title.lower().split())
                title_matches = len(query_words.intersection(title_words))
                score += title_matches * 0.5
            
            if paper.abstract:
                abstract_words = set(paper.abstract.lower().split())
                abstract_matches = len(query_words.intersection(abstract_words))
                score += abstract_matches * 0.1
            
            # Бонус за наличие DOI
            if paper.doi:
                score += 0.2
            
            # Бонус за свежесть публикации
            if paper.publication_date:
                if isinstance(paper.publication_date, str):
                    try:
                        paper.publication_date = datetime.fromisoformat(paper.publication_date)
                    except ValueError:
                        paper.publication_date = parse(paper.publication_date).date().isoformat()
                years_ago = (datetime.now() - paper.publication_date).days / 365.25
                if years_ago < 5:
                    score += (5 - years_ago) * 0.1
            paper.semantic_score = score
        return sorted(papers, key=lambda p: p.semantic_score, reverse=True)

    def get_search_statistics(self, search_results: Dict[str, SearchResult]) -> Dict[str, Any]:
        """
        Получить статистику поиска.
        
        Args:
            search_results: Результаты поиска
            
        Returns:
            Словарь со статистикой
        """
        stats = {
            'total_services': len(search_results),
            'successful_services': 0,
            'failed_services': 0,
            'total_papers': 0,
            'papers_by_service': {},
            'errors': {}
        }
        
        for service_name, result in search_results.items():
            if result.success:
                stats['successful_services'] += 1
                stats['total_papers'] += len(result.papers)
                stats['papers_by_service'][service_name] = len(result.papers)
            else:
                stats['failed_services'] += 1
                stats['errors'][service_name] = result.error
        
        return stats
    
    async def get_arxiv_paper_by_id(self, arxiv_id: str, full_text: bool=False) -> Optional[Paper]:
        """Получает статью ArXiv по ID."""
        if 'arxiv' not in self._services:
            logger.warning("ArXiv сервис недоступен")
            return None
            
        try:
            arxiv_service = self._services['arxiv']
            async with arxiv_service:
            
                if full_text:
                    # Получаем полную версию статьи
                    return await arxiv_service.get_full_text_by_id(arxiv_id)
                # Создаем URL для ArXiv статьи
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
                return await arxiv_service.get_paper_by_url(arxiv_url)
        except Exception as e:
            logger.error(f"Ошибка при получении ArXiv статьи {arxiv_id}: {e}")
            return None
    
    async def get_pubmed_paper_by_id(self, pubmed_id: str, full_text: bool = False) -> Optional[Paper]:
        """Получает статью PubMed по ID."""
        if 'ncbi' not in self._services:
            logger.warning("NCBI сервис недоступен")
            return None
            
        try:
            ncbi_service = self._services['ncbi']
            async with ncbi_service:
            
                if full_text:
                    # Получаем полную версию статьи
                    return await ncbi_service.get_full_text_by_id(pubmed_id)
                # Создаем URL для PubMed статьи
                pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/"
                return await ncbi_service.get_paper_by_url(pubmed_url)
        except Exception as e:
            logger.error(f"Ошибка при получении PubMed статьи {pubmed_id}: {e}")
            return None
    
    async def get_ieee_paper_by_id(self, ieee_id: str, full_text: bool = False) -> Optional[Paper]:
        """Получает статью IEEE по ID."""
        if 'ieee' not in self._services:
            logger.warning("IEEE сервис недоступен")
            return None
            
        try:
            ieee_service = self._services['ieee']
            async with ieee_service:
            
                if full_text:
                    # Получаем полную версию статьи
                    return await ieee_service.get_full_text_by_id(ieee_id)
                # Создаем URL для IEEE статьи
                ieee_url = f"https://ieeexplore.ieee.org/document/{ieee_id}"
                return await ieee_service.get_paper_by_url(ieee_url)
        except Exception as e:
            logger.error(f"Ошибка при получении IEEE статьи {ieee_id}: {e}")
            return None
    
    async def get_paper_by_doi(self, doi: str, full_text: bool = False) -> Optional[Paper]:
        """Получает статью по DOI через Semantic Scholar."""
        # Добавляем Semantic Scholar сервис если его нет
        if not self._services.get('semantic_scholar'):
            from services.search.semantic_scholar_service import SemanticScholarSearcher
            self._services['semantic_scholar'] = SemanticScholarSearcher()
            
        try:
            ss_service = self._services['semantic_scholar']
            async with ss_service:
                if full_text:
                # Получаем полную версию статьи
                    return await ss_service.get_full_text_by_id(doi)
                # Ищем статью по DOI через Semantic Scholar
                results = await ss_service.search_papers(doi, limit=1)
                if results:
                    return results[0]
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении статьи по DOI {doi}: {e}")
            return None
    
    async def get_paper_by_url_part(self, url_part: str) -> Optional[Paper]:
        """
        Пытается восстановить статью по части URL.
        Это упрощенная реализация - в реальности нужна более сложная логика.
        """
        # Пробуем разные варианты восстановления URL
        if re.search(r'[a-zA-Z]', url_part.split('/')[-1]):
            possible_urls = [f"https://www.semanticscholar.org/paper/{url_part}"]
        else:
            possible_urls = [
                f"https://www.semanticscholar.org/paper/{url_part}",
                f"https://arxiv.org/abs/{url_part}",
                f"https://pubmed.ncbi.nlm.nih.gov/{url_part}",
                f"https://ieeexplore.ieee.org/document/{url_part}",
        ]
        
        for url in possible_urls:
            paper = await self.get_paper_by_url(url)
            if paper:
                return paper
        
        logger.warning(f"Не удалось восстановить статью по части URL: {url_part}")
        return None
    
    async def get_paper_by_title_hash(self, title_hash: int, user_id: Optional[int] = None, full_text: bool = False) -> Optional[Paper]:
        """
        Получает статью по хешу заголовка из базы данных.
        
        Args:
            title_hash: Хеш заголовка статьи
            user_id: ID пользователя (если нужно искать в библиотеке пользователя)
        """
        if user_id is None:
            logger.warning(f"Поиск по хешу заголовка {title_hash} требует указания user_id")
            return None
            
        try:
            from database import SQLDatabase as db
            paper_data = await db.get_paper_by_title_hash(user_id, title_hash)
            
            if paper_data:
                # Преобразуем данные из БД в объект Paper
                return Paper(
                    title=paper_data.get('title', ''),
                    authors=paper_data.get('authors', []),
                    abstract=paper_data.get('abstract', ''),
                    doi=paper_data.get('doi', paper_data.get('DOI', '')),
                    publication_date=datetime.fromisoformat(paper_data.get('publication_date')),
                    journal=paper_data.get('journal', ''),
                    keywords=paper_data.get('keywords', []),
                    url=paper_data.get('url', ''),
                    external_id=paper_data.get('external_id', ''),
                    source=paper_data.get('source', ''),
                    source_metadata=paper_data.get('source_metadata', {})
                )
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении статьи по хешу заголовка {title_hash}: {e}")
            return None

    async def get_paper_by_identifier(self, callback_type: str, callback_value: str, user_id: Optional[int] = None, full_text: bool = False) -> Optional[Paper] | str:
        """
        Универсальный метод для получения статьи по различным типам идентификаторов.
        
        Args:
            callback_type: Тип идентификатора (arxiv, pubmed, ieee, doi, url, hash)
            callback_value: Значение идентификатора
            user_id: ID пользователя (нужен для поиска по хешу заголовка)
            full_text: Флаг, указывающий, нужно ли получать полный текст статьи
        Returns:
            Paper: объект если не full_text
            str: полный текст статьи если full_text
            None если статья не найдена
        """
        try:
            if callback_type == 'arxiv':
                return await self.get_arxiv_paper_by_id(callback_value, full_text=full_text)
            elif callback_type == 'pubmed' or callback_type == 'pmc' or callback_type.lower() == 'ncbi':
                return await self.get_pubmed_paper_by_id(callback_value, full_text=full_text)
            elif callback_type == 'ieee':
                return await self.get_ieee_paper_by_id(callback_value, full_text=full_text)
            elif callback_type == 'doi':
                return await self.get_paper_by_doi(callback_value, full_text=full_text)
            elif callback_type == 'url':
                return await self.get_paper_by_url_part(callback_value)
            elif callback_type == 'hash':
                return await self.get_paper_by_title_hash(callback_value, user_id, full_text=full_text)
            else:
                logger.warning(f"Неизвестный тип идентификатора: {callback_type}")
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении статьи по идентификатору {callback_type}:{callback_value}: {e}")
            return None

    async def fetch_full_texts_for_papers(
        self,
        papers: List[Paper],
        max_chars_per_text: int = 40000,
        concurrent: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Получить полный текст для списка статей с использованием доступных источников.

        Логика:
        - Пытаемся получить openAccess PDF через Semantic Scholar по DOI/PMID/arXiv/IEEE id
        - Для arXiv делаем дополнительный fallback на прямую загрузку PDF

        Returns: список словарей с метаданными и полным текстом/аннотацией
        { title, authors, year, journal, url, source, doi, id, abstract, text }
        """
        # Гарантируем наличие Semantic Scholar сервиса
        if 'semantic_scholar' not in self._services:
            self._services['semantic_scholar'] = SemanticScholarSearcher()

        def _get_s2_paper_id(p: Paper) -> str:
            pid = None
            # Prefer DOI first
            if p.doi:
                pid = f'DOI:{p.doi.strip()}'
            elif p.external_id and p.source:
                if p.source == 'arxiv':
                    pid = f'ARXIV:{p.external_id.strip()}'
                elif p.source == 'pubmed':
                    pid = f'PUBMED:{p.external_id.strip()}'
                elif p.source == 'PMC':
                    pid = f'PMC:{p.external_id.strip()}'
                elif p.source == 'ieee':
                    pid = f'IEEE:{p.external_id.strip()}'
            elif p.url:
                pid = p.url.rstrip('/').split('/')[-1]
            elif p.title:
                pid = p.title.strip().lower().replace(' ', '_')[:64]
            return pid

        async def _fetch_one(p: Paper) -> Dict[str, Any]:
            # --- Пытаемся получить полный текст статьи из источника p.source
            text: Optional[str] = None
            s2_id = _get_s2_paper_id(p)
            source = (p.source or '').lower()
            if source and source in self._services.keys():
                text = await self._services[source].get_full_text_by_id(p['external_id'])
            # --- Фоллбек: пытаемся получить текст из других источников
            if text is None:
                source = p['source']
                logger.debug(f"Source for {p.external_id[:15]}: {source}")
                
                try:
                    text = await self._services['semantic_scholar'].get_full_text_by_id(s2_id)
                    
                except Exception as e:
                    logger.error(f'Ошибка при поиске через S2: {e}')
                    

            # ограничиваем размер текста, если он слишком большой
            if text:
                text = text[:max_chars_per_text]
            else:
                text = ''

            # формируем результат
            year = None
            try:
                dt = p.publication_date
                if hasattr(dt, 'year'):
                    year = dt.year
                elif isinstance(dt, str) and len(dt) >= 4 and dt[:4].isdigit():
                    year = int(dt[:4])
            except Exception:
                year = None

            return {
                'title': p.title or '',
                'authors': p.authors or [],
                'year': year,
                'journal': p.journal or '',
                'url': p.url or '',
                'source': (p.source or '').lower(),
                'doi': p.doi or '',
                'id': p.external_id or '',
                'abstract': p.abstract or '',
                'text': text,
            }

        if not papers:
            return []
        
        if concurrent:
            async with (
                self._services['semantic_scholar'] as s2_ss,
                self._services['arxiv'] as arxiv_ss,
                self._services['ncbi'] as ncbi_ss,
                self._services['ieee'] as ieee_ss):
                # Параллельный fetch для всех статей
                tasks = [asyncio.create_task(_fetch_one(p)) for p in papers]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                out: List[Dict[str, Any]] = []
                for r in results:
                    if isinstance(r, Exception):
                        logger.error(f"Full-text fetch error in batch: {r}")
                    else:
                        out.append(r)
                return out
        else:
            out: List[Dict[str, Any]] = []
            for p in papers:
                try:
                    out.append(await _fetch_one(p))
                except Exception as e:
                    logger.error(f"Full-text fetch error: {e}")
            return out