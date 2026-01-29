import asyncio
import dateutil
import httpx
from config import load_config
from config.constants import NCBI_API_BASE_URL, API_TIMEOUT_SECONDS
from services.utils.paper import Paper, PaperSearcher
from utils import setup_logger
from xml.etree import ElementTree as ET
from typing import Optional, Dict, Any
from services.utils.parse import parse_pdf_content

logger = setup_logger(
    name="ncbi_service_logger",
    log_file='logs/ncbi_service.log',
    level='INFO'
)


class NCBISearcher(PaperSearcher):

    def __init__(self):
        config = load_config()
        self.semaphore = asyncio.Semaphore(10) 
        self.api_key = config.NCBI_API_KEY
        if not self.api_key:
            logger.warning("NCBI_API_KEY is not set")
            raise ValueError("NCBI_API_KEY is required but not set in the configuration")
        self.client = None
        self.tool = "python_pubmed_adapter"
        
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=NCBI_API_BASE_URL,
            timeout=API_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.client:
            await self.client.aclose()
            
    async def _make_request(self, endpoint: str, params: dict) -> httpx.Response:
        """Выполняет HTTP запрос к NCBI API."""
        if self.api_key:
            params["api_key"] = self.api_key
        try:
            response = await self.client.get(endpoint, params=params)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise

    async def search_papers(self, query: str, limit: int = 10, filters: Optional[Dict[str, Any]] = None) -> list[Paper]:
        """
        Поиск статей по запросу в NCBI API.
        
        :param query: Запрос для поиска.
        :param limit: Максимальное количество результатов для возврата.
        :param filters: Фильтры для поиска (year, author и т.д.)
        :return: Список объектов Paper.
        """
        # Строим улучшенный запрос с фильтрами
        enhanced_query = self._build_enhanced_query(query, filters)
        
        params = {
            "db": "pubmed",
            "term": enhanced_query,
            "retmax": limit,
            "retmode": "xml",
            'sort': 'relevance'
        }
        if self.api_key:
            params["api_key"] = self.api_key
        response = await self._make_request('/esearch.fcgi',params)
        root = ET.fromstring(response.content)
        id_list = root.find("IdList")
        if id_list is None:
            logger.warning("No IDs found in search response")
            return []

        pmids = [id_elem.text for id_elem in id_list.findall("Id")]
        logger.info(f"Найдено {len(pmids)} статей для запроса: {query}")
        if not pmids:
            logger.warning("No PMIDs found in search response")
            return []

        if len(pmids) > 100:
            papers = []
            for i in range(0, len(pmids), 100):
                async with self.semaphore:
                    await asyncio.sleep(0.1)  
                    chunk = pmids[i:i + 100]
                    papers.extend(await self._fetch_papers_details(chunk))
        else:
            papers = await self._fetch_papers_details(pmids)
        
        logger.info(f"Найдено {len(papers)} статей для запроса: {query}")
        
        # Применяем дополнительную фильтрацию
        if filters:
            papers = await self._apply_post_filters(papers, filters)
            
        
        return papers
    
    async def _fetch_papers_details(self, pmids: list[str]) -> list[Paper]:
        """
        Получение подробной информации о статьях по их PMID.
        
        :param pmids: Список PMID статей.
        :return: Список объектов Paper.
        """
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml"
        }
        response = await self._make_request('/efetch.fcgi', params)
        root = ET.fromstring(response.content)
        
        papers = []
        for article in root.findall(".//PubmedArticle"):
            paper = self._parse_ncbi_article(article)
            if paper:
                papers.append(paper)
                
        return papers
    
    def _parse_ncbi_article(self, article: ET.Element) -> Paper:
        try:
            paper = Paper()
            medline_citation = article.find('.//MedlineCitation')
            if medline_citation is None:
                return None
            
            # PMID
            pmid_elem = medline_citation.find('PMID')
            if pmid_elem is not None:
                paper.external_id = pmid_elem.text
            paper.source = 'NCBI'
            
            # Заголовок
            title_elem = medline_citation.find('.//ArticleTitle')
            if title_elem is not None:
                paper.title = title_elem.text or ""
            
            # Авторы
            author_list = medline_citation.find('.//AuthorList')
            if author_list is not None:
                for author in author_list.findall('Author'):
                    last_name = author.find('LastName')
                    first_name = author.find('ForeName')
                    if last_name is not None:
                        author_name = last_name.text
                        if first_name is not None:
                            author_name = f"{first_name.text} {author_name}"
                        paper.authors.append(author_name)
            
            # Аннотация
            abstract_elem = medline_citation.find('.//Abstract/AbstractText')
            if abstract_elem is not None:
                paper.abstract = abstract_elem.text or ""
            
            # Журнал
            journal_elem = medline_citation.find('.//Journal/Title')
            if journal_elem is not None:
                paper.journal = journal_elem.text or ""
            
            # Дата публикации
            pub_date = medline_citation.find('.//PubDate')
            if pub_date is not None:
                year = pub_date.find('Year')
                month = pub_date.find('Month')
                day = pub_date.find('Day')
                
                date_parts = []
                if year is not None:
                    date_parts.append(year.text)
                if month is not None:
                    date_parts.append(month.text)
                if day is not None:
                    date_parts.append(day.text)
                paper.publication_date = dateutil.parser.parse('-'.join(date_parts)).isoformat(timespec='hours')
            # DOI
            article_ids = article.findall('.//ArticleId')
            for article_id in article_ids:
                if article_id.get('IdType') == 'doi':
                    paper.doi = article_id.text
                    break
            
            # URL
            if paper.external_id:
                paper.url = f"https://pubmed.ncbi.nlm.nih.gov/{paper.external_id}/"
            
            # Ключевые слова
            keyword_list = medline_citation.find('.//KeywordList')
            if keyword_list is not None:
                for keyword in keyword_list.findall('Keyword'):
                    if keyword.text:
                        paper.tags.append(keyword.text)
            
            return paper
            
        except Exception as e:
            logger.error(f"Ошибка парсинга статьи PubMed: {e}")
            return None
        
    async def get_paper_by_url(self, url: str) -> Paper:
        """
        Получение статьи по URL из NCBI API.
        
        :param url: URL статьи.
        :return: Объект Paper.
        """
        if not url.startswith("https://pubmed.ncbi.nlm.nih.gov/"):
            logger.error(f"Invalid PubMed URL: {url}")
            raise ValueError("Invalid PubMed URL")
        
        pmid = url.split('/')[-2]
        papers = await self._fetch_papers_details([pmid])
        return papers[0] if papers else None
    
    def _build_enhanced_query(self, query: str, filters: Optional[Dict[str, Any]] = None) -> str:
        """
        Строит улучшенный запрос для NCBI API с учетом фильтров
        
        Args:
            query: Базовый поисковый запрос
            filters: Фильтры поиска
            
        Returns:
            Улучшенный поисковый запрос
        """
        query_parts = [query]
        
        if filters:
            # Фильтр по автору
            if filters.get('author'):
                author = filters['author']
                query_parts.append(f'"{author}"[AU]')
                
            if filters.get('year'):
                year = str(filters['year'])
                is_later = year.startswith('>')
                is_earlier = year.startswith('<')
                year = year.lstrip('><')
                if is_later:
                    query_parts.append(f'{year}/01/01:3000/12/31[PDAT]')
                elif is_earlier:
                    query_parts.append(f'0000/01/01:{year}/12/31[PDAT]')
                else:
                    query_parts.append(f'{year}/01/01:{year}/12/31[PDAT]')
            
            if filters.get('journal'):
                journal = filters['journal']
                query_parts.append(f'"{journal}"[TA]')

        return ' AND '.join(query_parts)

    async def get_full_text_by_id(self, pmid: str) -> Optional[str]:
        """
        Получает полный текст или аннотацию статьи по PMID.
        Пайплайн:
        1. Найти PMCID по PMID.
        2. Если PMCID найден -> Попытаться получить PDF из PMC OA.
        3. Если PDF недоступен -> Попытаться получить полный текст из PMC XML.
        4. Если PMCID НЕ найден -> Получить аннотацию из PubMed.
        """
        # --- Полуачем PMCID ---
        pmcid = None
        params = {
            'db': 'pubmed',
            'linkname': 'pubmed_pmc',
            'id': pmid
        }
        try:
            resp = await self._make_request('elink.fcgi', params)
            resp.raise_for_status()
            xml_content = resp.content
            root = ET.fromstring(xml_content)
            link_set_db = root.find(".//LinkSetDb[DbTo='pmc']")
            if link_set_db is not None:
                link_id = link_set_db.find(".//Id")
                if link_id is not None and link_id.text:
                    pmcid = 'PMC' + link_id.text
        except httpx.RequestError as e:
            logger.error(f"Error fetching PMCID for PMID {pmid}: {e}")
            return None
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга XML-ответа от ELink: {e}")
            return None
        # --- Если PMCID НЕ найден: Фоллбэк на аннотацию из PubMed ---
        if not pmcid:
            logger.info(f"PMCID не найден для PMID {pmid}, переключаемся на аннотацию из PubMed.")
            try:
                params = {
                    'db': 'pubmed',
                    'id': pmid,
                    'retmode': 'xml'
                }
                xml_resp = await self._make_request('efetch.fcgi', params)
                xml_resp.raise_for_status()
                pm_root = ET.fromstring(xml_resp.content)
                abstract_nodes = pm_root.findall(".//Abstract/AbstractText")
                if abstract_nodes:
                    abstract_text = "\n".join(node.text.strip() for node in abstract_nodes if node.text)
                    if abstract_text:
                        return abstract_text
                logger.info(f"Аннотация не найдена для PMID {pmid}")
                return None
            except httpx.RequestError as e:
                logger.error(f"Error fetching abstract for PMID {pmid}: {e}")
                return None

        # --- Получаем полный текст статьи ---
        try:
            params = {
                'id': pmcid
            }
            url = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
            resp = await self._make_request(url, params)
            resp.raise_for_status()
            oa_root = ET.fromstring(resp.content)
            
            pdf_link_node = oa_root.find(f".//record[@pmcid='{pmcid}']/link[@format='pdf']")
            if pdf_link_node is not None:
                pdf_url = pdf_link_node.get('href')
                
                pdf_resp = await self.client.get(pdf_url)
                pdf_resp.raise_for_status()

                pdf_content = pdf_resp.content
                return parse_pdf_content(pdf_content, paper_id=pmcid, logger=logger)
        except httpx.RequestError as e:
            logger.error(f"Error fetching full text for PMCID {pmcid}: {e}")
            return None
        except ET.ParseError as e:
            logger.error(f"Error parsing XML response for PMCID {pmcid}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching full text for PMCID {pmcid}: {e}")
            return None

        # --- Фоллбек на XML ---
        logger.warning(f"Полный текст не найден для PMCID {pmcid}, переключаемся на XML")
        try:
            params = {
                'db': 'pmc',
                'id': pmcid,
                'retmode': 'xml'
            }
            xml_resp = await self._make_request('efetch.fcgi', params)
            xml_resp.raise_for_status()
            xml_root = ET.fromstring(xml_resp.content) 
            body = xml_root.find('.//body')
            full_text = " ".join(
                t.strip() for t in (body if body is not None else xml_root)
                .itertext() if t.strip()
                )
            if not full_text:
                logger.warning(f"Полный текст не найден для PMCID {pmcid}")
                return None
            return full_text
        except httpx.RequestError as e:
            logger.error(f"Error fetching full text XML for PMCID {pmcid}: {e}")
            return None
            

    async def _apply_post_filters(self, papers: list[Paper], filters: Dict[str, Any]) -> list[Paper]:
        """
        Применяет дополнительные фильтры к результатам поиска
        
        Args:
            papers: Список статей для фильтрации
            filters: Словарь с фильтрами
            
        Returns:
            Отфильтрованный список статей
        """
        filtered_papers = papers
        logger.info(f"Фильтр по количеству цитат: {filters.get('citation_count')}")
        # Фильтр по количеству цитат
        if filters.get('citation_count'):
            citation_counts = filters['citation_count']
            url = 'https://api.semanticscholar.org/graph/v1/paper/batch'
            params = {'fields': 'citationCount'}
            js={"ids": [f'PMID:{paper.external_id}' for paper in papers]}
            logger.info(f'Первые элементы во втором чанке: {js["ids"][500:510]}')
            json_arr = []
            chunk_size = 500
            if len(js['ids']) > chunk_size:
                for i in range(0, len(js['ids']), chunk_size):
                    chunk = {"ids": js["ids"][i:i + chunk_size]}
                    try:
                        resp = await self.client.post(url, params=params, json=chunk)
                        resp.raise_for_status()
                        json_arr.extend(resp.json())
                    except Exception as e:
                        logger.error(f"Error in chunk {i}: {e} - Response: {resp.text if 'resp' in locals() else 'No response'}")
            else:
                resp = await self.client.post(url, params=params, json=js)
                resp.raise_for_status()
                json_arr = resp.json()
            for it in range(len(json_arr)):
                if json_arr[it] is None:
                    json_arr[it] = {'citationCount': -1}
            filtered_papers = [papers[i] for i in range(len(papers)) if int(json_arr[i]['citationCount']) >= int(citation_counts)]
        logger.info(f'Отфильтровано статей: {len(filtered_papers)}')
        return filtered_papers