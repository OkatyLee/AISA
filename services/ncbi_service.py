import httpx
from config import load_config
from config.constants import NCBI_API_BASE_URL, API_TIMEOUT_SECONDS
from services.paper import Paper, PaperSearcher
from utils import setup_logger
from xml.etree import ElementTree as ET


logger = setup_logger(
    name="ncbi_service_logger",
    log_file='logs/ncbi_service.log',
    level='INFO'
)


class NCBISearcher(PaperSearcher):

    def __init__(self):
        config = load_config()
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

    async def search_papers(self, query: str, limit: int = 10) -> list[Paper]:
        """
        Поиск статей по запросу в NCBI API.
        
        :param query: Запрос для поиска.
        :param limit: Максимальное количество результатов для возврата.
        :return: Список объектов Paper.
        """
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": min(limit, 200),
            "retmode": "xml"
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
        if not pmids:
            logger.warning("No PMIDs found in search response")
            return []
        
        return await self._fetch_papers_details(pmids)
    
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
                
                paper.publication_date = '-'.join(date_parts)
            
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
                        paper.keywords.append(keyword.text)
            
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