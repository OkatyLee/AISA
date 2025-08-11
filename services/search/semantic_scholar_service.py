
from datetime import datetime
from urllib.parse import urlparse
from services.utils.paper import Paper, PaperSearcher
import httpx
from dateutil.parser import parse
from typing import List, Dict, Any, Optional
import re
from utils.logger import setup_logger
import asyncio
import time

logger = setup_logger(
    "SemanticScholarService"
)

class SemanticScholarSearcher(PaperSearcher):

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    FIELD = "title,authors,abstract,publicationDate,journal,venue,url,externalIds"
    DOI_REGEX = re.compile(r'^(10\.\d{4,9}/[-._;()/:A-Z0-9]+)$', re.IGNORECASE)

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self.api_key = None # не дали
        self._last_call_ts = 0.0
        self._min_interval = 1.0  # минимальный интервал между запросами в секундах
                
    async def __aenter__(self):
        if self._client is None:
            headers = {
                "User-Agent": "SemanticScholarService/1.0",
                "Accept": "application/json"
            }
            if self.api_key:
                headers["x-api-key"] = self.api_key
            
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30),
                headers=headers,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
            )
            return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    async def _make_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 5,
        base_backoff: float = 0.5
    ) -> Dict[str, Any]:
        """
        Выполняет GET-запрос к Semantic Scholar API.
        
        :param url: URL для запроса.
        :param params: Параметры запроса.
        :return: Ответ от API.
        """
        if self._client is None:
            raise RuntimeError("HTTP client is not initialized. Call __aenter__() first.")
        for attempt in range(max_retries):
            await self._rate_limit()
            try:
                resp = await self._client.get(url, params=params)
            except httpx.RequestError as e:
                # сетевые ошибки — ретрай с backoff
                logger.error(f"Network error: {e}")
                await asyncio.sleep(base_backoff * (2 ** attempt))
                continue

            # 2xx
            if 200 <= resp.status_code < 300:
                return resp.json()

            # 429 — уважаем Retry-After
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                sleep_s = float(retry_after) if retry_after else base_backoff * (2 ** attempt)
                logger.warning(f"429 Too Many Requests. Sleeping {sleep_s:.2f}s")
                await asyncio.sleep(sleep_s)
                continue

            # 5xx — ретрай
            if 500 <= resp.status_code < 600:
                logger.warning(f"Server error {resp.status_code}. Retrying...")
                await asyncio.sleep(base_backoff * (2 ** attempt))
                continue

            # 4xx (кроме 429) — не ретраим, логируем тело для диагностики
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            logger.error(f"HTTP {resp.status_code} for {url} params={params}. Body: {body}")
            # Возвращаем структурированную ошибку, чтобы вызывающая сторона приняла решение
            return {"error": {"status": resp.status_code, "body": body}}

        # Если все retries исчерпаны — финальная ошибка
        raise RuntimeError("Exceeded max retries for request")
        
    def _parse_paper_data(self, paper_data: Dict[str, Any]) -> Paper:
        """
        Преобразует данные статьи из Semantic Scholar в объект Paper.
        
        :param paper_data: Данные статьи из API.
        :return: Объект Paper.
        """
        # Извлечение авторов
        authors = []
        if paper_data.get("authors"):
            authors = [author.get("name", "Unknown") for author in paper_data["authors"]]
        
        # Извлечение даты публикации
        publication_date = None
        if paper_data.get("publicationDate"):
            try:
                publication_date = datetime.strptime(paper_data["publicationDate"], "%Y-%m-%d")
            except ValueError:
                publication_date = parse(paper_data["publicationDate"])

        
        # Извлечение журнала
        journal = None
        if paper_data.get("journal"):
            journal = paper_data["journal"].get("name")
        elif paper_data.get("venue"):
            journal = paper_data["venue"]
        
        # Определение источника и внешнего ID
        external_id = None
        source = None
        source_metadata = {}
        
        external_ids = paper_data.get("externalIds", {})
        if external_ids:
            if external_ids.get("ArXiv"):
                source = "arxiv"
                external_id = external_ids["ArXiv"]
            elif external_ids.get("PubMed"):
                source = "pubmed"
                external_id = external_ids["PubMed"]
            elif external_ids.get("IEEE"):
                source = "ieee"
                external_id = external_ids["IEEE"]
            elif external_ids.get("DOI"):
                source = "doi"
                external_id = external_ids["DOI"]
            
            source_metadata = external_ids
            
        return Paper(
            title=paper_data.get("title", ""),
            authors=authors,
            abstract=paper_data.get("abstract"),
            doi=paper_data.get("doi") or external_ids.get("DOI"),
            publication_date=publication_date,
            journal=journal,
            keywords=paper_data.get("fieldsOfStudy", []),
            url=paper_data.get("url"),
            external_id=external_id,
            source=source,
            source_metadata=source_metadata
        )
        
    async def _rate_limit(self):
        # простой фиксированный интервал
        now = time.monotonic()
        delay = self._min_interval - (now - self._last_call_ts)
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_call_ts = time.monotonic()
        
    async def search_papers(self, query, limit = 10, filters = None):
        is_doi = self.DOI_REGEX.match(query)
        if is_doi:
            logger.info(f'Выполняем поиск по DOI {query}')
            paper_id = f'DOI:{query}'
            url = f"{self.BASE_URL}/paper/{paper_id}"
            params = {"fields" : self.FIELD}
            try:
                paper_data = await self._make_request(url, params)
                if "error" in paper_data:
                     logger.warning(f"Could not find paper with DOI: {query}. API response: {paper_data.get('body')}")
                     return []
                paper = self._parse_paper_data(paper_data)
                return [paper]
            except Exception as e:
                logger.error(f"Error occurred while searching paper by DOI {query}: {e}")
                return []
        else:
            url = f"{self.BASE_URL}/paper/search"

            params = {
                "query": query,
                "limit": limit,
                "fields": self.FIELD,
            }
            
            if filters:
                for k in ("offset", "year", "yearFilter", "fieldsOfStudy", "venue"):
                    if k in filters:
                        params[k] = filters[k]
            
            try:
                papers_json = await self._make_request(url, params=params)
                if "error" in papers_json or "data" not in papers_json:
                    return []
                papers = []

                for paper_data in papers_json.get("data", []):
                    paper = self._parse_paper_data(paper_data)
                    papers.append(paper)
                return papers
            except Exception as e:
                logger.error(f"Error occurred while searching papers: {e}")
                return []
        
    def _extract_paper_id_from_url(self, url: str) -> Optional[str]:
        """
        Извлекает идентификатор статьи из URL.
        
        :param url: URL статьи.
        :return: Идентификатор статьи или None, если не удалось извлечь.
        """
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.strip("/").split("/")
        
        if len(path_parts) >= 2 and path_parts[0] == "paper":
            # Извлекаем последнюю часть как ID
            paper_id = path_parts[-1]
            if paper_id:
                return paper_id
        
        raise ValueError("Cannot extract paper ID from URL")
    
    async def get_paper_by_url(self, url: str) -> Paper:
        try:
            paper_id = self._extract_paper_id_from_url(url)
        except ValueError as e:
            raise ValueError(f"Invalid URL: {str(e)}")
        
        api_url = f"{self.BASE_URL}/paper/{paper_id}"
        params = {
            "fields": self.FIELD
        }
        
        try:
            paper_data = await self._make_request(api_url, params)
            return self._parse_paper_data(paper_data)

        except httpx.HTTPError as e:
            if "not found" in str(e).lower():
                logger.error(f"Paper not found for URL: {url}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting paper: {str(e)}")
