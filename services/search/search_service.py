import asyncio
from typing import List, Dict, Any, Optional

from services.utils.paper import Paper, PaperSearcher
from services.search import ArxivSearcher
from services.search import IEEESearcher
from services.search import NCBISearcher
from utils import setup_logger

logger = setup_logger(
    name="search_service_logger",
    log_file='logs/search_service.log',
    level='INFO'
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
                'arxiv': ArxivSearcher(),
                'ieee': IEEESearcher(),
                'ncbi': NCBISearcher()
            }
        else:
            self._services = services
        
        logger.info(f"Инициализирован SearchService с сервисами: {list(self._services.keys())}")

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
        concurrent: bool = True
    ) -> Dict[str, SearchResult]:
        """
        Поиск статей через выбранные сервисы.
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов на сервис
            services: Список сервисов для использования. Если None, используются все
            concurrent: Выполнять поиск параллельно
            
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
            return await self._search_concurrent(query, limit, available_services)
        else:
            return await self._search_sequential(query, limit, available_services)

    async def _search_concurrent(
        self,
        query: str,
        limit: int,
        services: Dict[str, PaperSearcher]
    ) -> Dict[str, SearchResult]:
        """Параллельный поиск через все сервисы."""
        tasks = []
        
        for name, service in services.items():
            task = asyncio.create_task(
                self._search_single_service(name, service, query, limit),
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
        services: Dict[str, PaperSearcher]
    ) -> Dict[str, SearchResult]:
        """Последовательный поиск через сервисы."""
        results = {}
        
        for name, service in services.items():
            try:
                result = await self._search_single_service(name, service, query, limit)
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
        limit: int
    ) -> SearchResult:
        """Поиск через один сервис."""
        try:
            async with service:
                papers = await service.search_papers(query, limit)
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
        
        return None

    def aggregate_results(
        self,
        search_results: Dict[str, SearchResult],
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
                logger.warning(f"Пропускаем результаты от {service_name} из-за ошибки: {result.error}")
        
        # Удаляем дубликаты
        if remove_duplicates:
            all_papers = self._remove_duplicates(all_papers)
            logger.info(f"После удаления дубликатов осталось {len(all_papers)} статей")
        
        # Сортируем
        all_papers = self._sort_papers(all_papers, sort_by)
        
        return all_papers

    def _remove_duplicates(self, papers: List[Paper]) -> List[Paper]:
        """Удалить дубликаты статей на основе DOI, URL или названия."""
        seen = set()
        unique_papers = []
        
        for paper in papers:
            # Создаем ключ для идентификации дубликатов
            key = None
            
            # Приоритет: DOI > URL > нормализованное название
            if paper.doi:
                key = ('doi', paper.doi.lower())
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

    def _sort_papers(self, papers: List[Paper], sort_by: str) -> List[Paper]:
        """Сортировать статьи по заданному критерию."""
        if sort_by == 'date':
            return sorted(papers, key=lambda p: p.publication_date or '', reverse=True)
        elif sort_by == 'title':
            return sorted(papers, key=lambda p: p.title.lower())
        else:  # relevance или любой другой критерий
            # Для релевантности оставляем исходный порядок от сервисов
            return papers

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