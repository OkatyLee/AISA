
from datetime import datetime
from urllib.parse import quote
import fitz
from services.utils.paper import Paper, PaperSearcher
import httpx
from dateutil.parser import parse
from typing import List, Dict, Any, Optional
import re
from utils.logger import setup_logger
import asyncio
import time

logger = setup_logger(
    "ss_service_logger",
    level="DEBUG"
)

class SemanticScholarSearcher(PaperSearcher):

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    FIELD = "title,authors,abstract,publicationDate,journal,venue,url,externalIds,year,fieldsOfStudy"
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
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                follow_redirects=True
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
        elif paper_data.get("year"):
            try:
                publication_date = datetime.strptime(str(paper_data["year"]), "%Y")
            except ValueError:
                publication_date = parse(str(paper_data["year"]))

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
            elif external_ids.get("PubMedCentral"):
                source = "pmc"
                external_id = external_ids["PubMedCentral"]
            elif external_ids.get("IEEE"):
                source = "ieee"
                external_id = external_ids["IEEE"]
            elif external_ids.get("DOI"):
                source = "doi"
                external_id = external_ids["DOI"]
            
            source_metadata = external_ids
        logger.info(paper_data.get('fieldsOfStudy'))
        return Paper(
            title=paper_data.get("title", ""),
            authors=authors,
            abstract=paper_data.get("abstract"),
            doi=paper_data.get("doi") or external_ids.get("DOI"),
            publication_date=publication_date,
            journal=journal,
            tags=paper_data.get("fieldsOfStudy", []),
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
        
    def setup_params(self, params: Dict[str, str], filters: Dict[str, str]) -> Dict[str, str]:
        """
        Устанавливает параметры запроса для Semantic Scholar API.
        
        :param params: Словарь параметров.
        :return: Обновленный словарь параметров.
        """
        if filters.get("year"):
            year = filters["year"]
            if isinstance(year, int):
                year = str(year)
            is_later = year.startswith(">")
            is_earlier = year.startswith("<")  
            year = year.lstrip('<>')
            if is_later:
                params['year'] = f'{year}-'
            if is_earlier:
                params['year'] = f'-{year}'
            else:
                params['year'] = year
        if filters.get("citation_count"):
            params['sort'] = 'citationCount:desc'
            params['minCitationCount'] = filters["citation_count"]
        if filters.get("journal"):
            params['venue'] = filters["journal"]
        return params

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
            if filters.get('author'):
                author_id = await self._search_author(filters['author'])
                if not author_id:
                    logger.error(f"Could not find author: {filters['author']}")
                    return []

                # Шаг 2: Формируем URL для получения статей автора
                url = f"{self.BASE_URL}/author/{author_id}/papers"
                params = {
                    "query": query,  # Можно передать основной запрос для фильтрации по ключевым словам
                    "limit": limit,
                    "fields": self.FIELD,
                }
                
                # Добавляем year, если указан (поддерживается в этом endpoint)
                if filters.get("year"):
                    year = filters["year"]
                    if isinstance(year, int):
                        year = str(year)
                    is_later = year.startswith(">")
                    is_earlier = year.startswith("<")
                    
                    if is_later:
                        params['year'] = f'{year}-'
                    elif is_earlier:
                        params['year'] = f'-{year}'
                    else:
                        params['year'] = year
                
                # Для citation_count можно использовать sort, но не minCitationCount
                if filters.get("citation_count"):
                    params['sort'] = 'citationCount:desc'  # Сортировка по цитированиям (desc для убывания)
                    min_citations = filters["citation_count"]
                else:
                    min_citations = None
                
                # Venue не поддерживается, запомним для локальной фильтрации
                venue_filter = filters.get("journal")
                
                try:
                    papers_json = await self._make_request(url, params=params)
                    if "error" in papers_json or "data" not in papers_json:
                        return []
                    
                    papers = []
                    for paper_data in papers_json.get("data", []):
                        # Локальная фильтрация для неподдерживаемых параметров
                        if min_citations and paper_data.get("citationCount", 0) < min_citations:
                            continue
                        if venue_filter and paper_data.get("venue", "").lower() != venue_filter.lower():
                            continue
                        
                        paper = self._parse_paper_data(paper_data)
                        papers.append(paper)
                    
                    return papers
                except Exception as e:
                    logger.error(f"Error occurred while searching papers by author: {e}")
                    return []

            else:
                url = f"{self.BASE_URL}/paper/search"

                params = {
                    "query": query,
                    "limit": limit,
                    "fields": self.FIELD,
                }
                params = self.setup_params(params, filters or {})
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
    
    async def _search_author(self, author_name: str) -> str | None:
        url = f"{self.BASE_URL}/author/search"
        params = {
            "query": author_name,
            "limit": 1, 
            "fields": "authorId"
        }
        try:
            response = await self._make_request(url, params=params)
            if "data" in response and response["data"]:
                return response["data"][0]["authorId"]
            return None
        except Exception as e:
            logger.error(f"Error searching author: {e}")
            return None
        
    def _extract_paper_id_from_url(self, url: str) -> Optional[str]:
        """
        Извлекает идентификатор статьи из URL.
        
        :param url: URL статьи.
        :return: Идентификатор статьи или None, если не удалось извлечь.
        """
        url = url.lower()  # Для case-insensitive поиска

        # Semantic Scholar: /paper/<hash-id>
        ss_pattern = re.compile(r"semanticscholar\.org/paper/([a-f0-9]{10,40})(?:$|[^a-f0-9])")
        match = ss_pattern.search(url)
        if match:
            return match.group(1)

        # ArXiv: arxiv.org/abs/<id> или arxiv.org/pdf/<id>.pdf
        arxiv_pattern = re.compile(r"arxiv\.org/(abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:\.pdf)?")
        match = arxiv_pattern.search(url)
        if match:
            return f"ARXIV:{match.group(2)}"

        # PubMed: pubmed.ncbi.nlm.nih.gov/<pmid>/
        pubmed_pattern = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)")
        match = pubmed_pattern.search(url)
        if match:
            return f"PMID:{match.group(1)}"

        # PMC (PubMed Central): ncbi.nlm.nih.gov/pmc/articles/PMC<id>/
        pmc_pattern = re.compile(r"ncbi\.nlm\.nih\.gov/pmc/articles/(pmc\d+)")
        match = pmc_pattern.search(url)
        if match:
            return match.group(1).upper()

        # IEEE Xplore: ieeexplore.ieee.org/document/<id>
        ieee_pattern = re.compile(r"ieeexplore\.ieee\.org/document/(\d+)")
        match = ieee_pattern.search(url)
        if match:
            return f"IEEE:{match.group(1)}"

        # DOI: doi.org/<doi> или dx.doi.org/<doi>
        doi_pattern = re.compile(r"(?:dx\.)?doi\.org/(.+)")
        match = doi_pattern.search(url)
        if match:
            return f"DOI:{match.group(1)}"

        return None
    
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
            return None

    async def get_full_text_by_id(self, paper_id: str) -> Optional[str]:
        """
        Попытаться получить текст PDF по paper_id.
        Поддерживает: S2 internal id, PMID, DOI, arXiv и попытки по IEEE (через префиксы и/или поиск).
        Возвращает текст (str) или None.
        """
        ARXIV_RE = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5}(v\d+)?|[a-z\-]+/\d{7})(v\d+)?$", re.IGNORECASE)
        DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)

        fields = 'title,isOpenAccess,openAccessPdf'
        pid = (paper_id or "").strip()
        if not pid:
            logger.error("Empty paper_id provided")
            return None

        # нормализованная нижняя версия для детекции
        pid_lower = pid.lower()

        # Собираем кандидатов (в порядке предпочтения)
        candidates: List[str] = []

        # Если пользователь уже передал с префиксом, попробуем как есть
        if ':' in pid and not pid.startswith("http"):
            candidates.append(pid)

        # DOI
        if DOI_RE.match(pid):
            candidates.append(f"DOI:{pid}")

        # arXiv (разные варианты записи)
        m = ARXIV_RE.match(pid)
        if m:
            arxiv_id = m.group(1)
            candidates.append(f"ARXIV:{arxiv_id}")

        # Чистые цифры — вероятно PubMed
        if pid.isdigit():
            candidates.append(f"PMID:{pid}")

        # Попроёбовать варианты для IEEE (не всегда присутствует как externalId в S2).
        # Пробуем несколько возможных префиксов — если Semantic Scholar не поддерживает,
        # дальше сработает fallback через поиск.
        if pid_lower.startswith("ieee") or pid.isdigit() or pid.startswith("Xplore:") or "ieeexplore" in pid_lower:
            candidates.append(f"IEEE:{pid}")
            candidates.append(f"IEEEXPLORE:{pid}")
            candidates.append(pid)  # raw value (вдруг это S2 paperId)

        # В конце добавим сырое значение — на случай S2 internal id
        candidates.append(pid)

        # Уникализируем порядок, сохраняя порядок появления
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)
        candidates = unique_candidates

        # Вспомогательная функция для получения paper JSON по конкретному идентификатору
        async def fetch_paper_json(candidate_id: str) -> Optional[dict]:
            url = f"{self.BASE_URL}/paper/{quote(candidate_id, safe='')}"
            try:
                data = await self._make_request(url, params={"fields": fields})
            except Exception as e:
                logger.error(f"Request failed for candidate '{candidate_id}': {e}")
                return None
            if not data or isinstance(data, dict) and data.get("error"):
                return None
            return data

        # Пробуем кандидатов
        for candidate in candidates:
            data = await fetch_paper_json(candidate)
            if not data:
                continue

            is_open = data.get("isOpenAccess", False)
            if not is_open:
                logger.info(f"Found paper for '{candidate}' but it is not open access — пропускаем.")
                continue

            oap = data.get("openAccessPdf")
            open_pdf_url = None
            if isinstance(oap, dict):
                open_pdf_url = oap.get("url")
            elif isinstance(oap, str):
                open_pdf_url = oap

            if not open_pdf_url:
                logger.info(f"Paper '{candidate}' is open access but no openAccessPdf URL present — пропускаем.")
                continue

            # Получаем PDF
            try:
                pdf_resp = await self._client.get(open_pdf_url)
            except Exception as e:
                logger.exception(f"Failed to fetch PDF at '{open_pdf_url}' for '{candidate}': {e}")
                continue

            if pdf_resp.status_code == 404:
                logger.error(f"PDF not found (404) at '{open_pdf_url}' for paper '{candidate}'")
                continue

            try:
                pdf_resp.raise_for_status()
            except Exception as e:
                logger.exception(f"Error fetching PDF for '{candidate}': {e}")
                continue

            pdf_data = pdf_resp.content
            if not pdf_data:
                logger.error(f"Empty PDF content for '{candidate}' from '{open_pdf_url}'")
                continue

            # Парсим PDF в текст
            try:
                doc = fitz.open(stream=pdf_data, filetype="pdf")
                text_parts = [page.get_text() for page in doc]
                doc.close()
                return "\n".join(text_parts)
            except Exception as e:
                logger.exception(f"Failed to parse PDF for '{candidate}': {e}")
                continue

        # --- Fallback: поиск через /paper/search (если прямые попытки не сработали) ---
        # Попробуем найти по исходному идентификатору (или по части DOI/arXiv), взять первый результат
        try:
            search_url = f"{self.BASE_URL}/paper/search"
            params = {"query": pid, "fields": "paperId,isOpenAccess,openAccessPdf", "limit": 1}
            search_json = await self._make_request(search_url, params=params)
        except Exception as e:
            logger.exception(f"Search request failed for '{pid}': {e}")
            search_json = None

        if search_json and not search_json.get("error"):
            try:
                results = search_json.get("data") or search_json.get("results") or search_json.get("papers") or []
                if not results and isinstance(search_json.get("total"), int) and search_json.get("total") > 0:
                    results = search_json.get("items", [])
                if results:
                    first = results[0]
                    paperId = first.get("paperId") if isinstance(first, dict) else None
                    if paperId:
                        logger.info(f"Search fallback found paperId {paperId} for query '{pid}' — пытаемся загрузить PDF.")
                        data = await fetch_paper_json(paperId)
                        if data:
                            is_open = data.get("isOpenAccess", False)
                            if is_open:
                                oap = data.get("openAccessPdf")
                                open_pdf_url = oap.get("url") if isinstance(oap, dict) else (oap if isinstance(oap, str) else None)
                                if open_pdf_url:
                                    try:
                                        pdf_resp = await self._client.get(open_pdf_url)
                                        pdf_resp.raise_for_status()
                                        pdf_data = pdf_resp.content
                                        doc = fitz.open(stream=pdf_data, filetype="pdf")
                                        text_parts = [page.get_text() for page in doc]
                                        doc.close()
                                        return "\n".join(text_parts)
                                    except Exception as e:
                                        logger.exception(f"Failed to fetch/parse PDF during search-fallback for '{paperId}': {e}")
                            else:
                                logger.info(f"Search-fallback found {paperId} but paper is not open access.")
            except Exception as e:
                logger.error(f"Failed to handle search response for '{pid}': {e}")

        logger.error(f"Paper not found or not accessible for id '{pid}' (candidates tried: {candidates})")
        return None

    async def get_recommendation_for_single_paper(self, paper_id: str, limit:int = 10) -> Optional[List[Paper]]:
        try:
            url = f'https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{paper_id}'
            params = {
                "limit": limit,
                'fields': self.FIELD
            }
            resp = await self._make_request(url, params=params)
            data = resp['recommendedPapers']
            papers = [self._parse_paper_data(p) for p in data]
            return papers
        
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при получении рекомендаций для статьи '{paper_id}': {e}")
            return None
        
        except Exception as e:
            logger.error(f"Неожиданная ошибка при получении рекомендаций для статьи '{paper_id}': {e}")
            return None

    def _get_s2_paper_id(self, p: Paper) -> str:
            pid = p.external_id
            if p.doi:
                pid = f'DOI:{p.doi.strip()}'
            elif p.external_id and p.source:
                if p.source == 'arxiv':
                    pid = f'ARXIV:{p.external_id.strip()}'
                elif p.source == 'pubmed' or p.source == 'ncbi':
                    pid = f'PUBMED:{p.external_id.strip()}'
                elif p.source == 'PMC':
                    pid = f'PMC:{p.external_id.strip()}'
                elif p.source == 'ieee':
                    pid = f'IEEE:{p.external_id.strip()}'
            elif p.url:
                pid = self._extract_paper_id_from_url(p.url)
            elif p.title:
                pid = p.title.strip().lower().replace(' ', '_')[:64]
            return pid
    
    async def get_recommendations_for_multiple_papers(self, papers: List[Paper], limit: int = 50):

        url = "https://api.semanticscholar.org/recommendations/v1/papers"
        paper_ids = [self._get_s2_paper_id(paper) for paper in papers]
        import json
        payload = json.dumps({
            'positivePaperIds': paper_ids,
            "negativePaperIds": [],
        })
        headers = {
            "Content-Type": "application/json"
        }
        params = {
            'fields': self.FIELD,
            'limit': limit
        }
        async with self._client as client:
            response = await client.post(
                url=url, 
                headers=headers,
                params=params,
                data=payload)
            response.raise_for_status()
            papers = response.json()['recommendedPapers']
            papers = [self._parse_paper_data(p) for p in papers]
            return papers
