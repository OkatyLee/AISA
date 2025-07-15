import httpx
from config import load_config
from typing import List, Dict, Any
import xml.etree.ElementTree as ET
from datetime import datetime
from utils import setup_logger
import logging
from aiogram.utils.markdown import hbold, hitalic, hlink

logger = setup_logger(name="arxiv_service_logger", log_file="logs/arxiv_service.log", level=logging.INFO)

class ArxivSearcher:

    def __init__(self):
        self.session = None
        self.MAX_RESULTS = load_config().MAX_RESULTS

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
        """Поиск статей в ArXiv API"""
        try:

            url = "https://export.arxiv.org/api/query"
            params = {
                'search_query': f'all:{query}',
                'start': 0,
                'sortBy': 'relevance',
                'sortOrder': 'descending',
                "max_results": self.MAX_RESULTS 
            }

            response = await self.session.get(url, params=params)
            response.raise_for_status()

            return self._parse_arxiv_response(response.text)
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка: {e.response.status_code} - {e.response.text}")
            return []
        except httpx.TimeoutException as e:
            logger.error(f"Время ожидания ответа истекло: {e}")
            return []
        except httpx.ConnectError as e:
            logger.error(f"Ошибка соединения: {e}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка: {e}")
            return []

    def _parse_arxiv_response(self, response_text: str) -> List[Dict[str, str]]:
        """Парсинг ответа ArXiv API"""
        try:
            papers = []
            root = ET.fromstring(response_text)

            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
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
                    
                link = entry.find('atom:id', namespaces)
                link_text = link.text.strip() if link is not None else ""
                
                authors = entry.findall('atom:author', namespaces)
                author_names = []
                for author in authors:
                    name = author.find('atom:name', namespaces)
                    if name is not None:
                        author_names.append(name.text.strip())
                        
                categories = []
                for category in entry.findall('atom:category', namespaces):
                    term = category.get('term')
                    if term:
                        categories.append(term)
                    
                    paper = {
                        'title': title_text,
                        'authors': author_names,
                        'link': link_text,
                        'published': formatted_date,
                        'summary': summary_text,
                        'categories': categories[:3]
                    }
                papers.append(paper)
            return papers
        except ET.ParseError as e:
            logger.error(f"Ошибка в парсинге XML: {e}")
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка: {e}")
            return []

def format_paper_message(paper: Dict[str, Any], index: int) -> str:
    """Форматирование информации о статье для вывода"""
    title = hbold(f"{index}. {paper['title']}")
    
    authors_text = ', '.join(paper['authors'][:3])
    if len(paper['authors']) > 3:
        authors_text += f" и еще {len(paper['authors']) - 3} автора"
    authors = hitalic(authors_text)
    
    date = f'Опубликовано: {paper["published"]}' if paper['published'] else 'Дата публикации не указана'
    categories = ''
    if paper['categories']:
        categories = ', '.join(paper['categories'])
    
    summary = f"📄 {paper['summary']}"
    
    # Ссылка
    link = hlink("🔗 Читать статью", paper['link'])
    
    # Собираем всё вместе
    parts = [title, authors, date]
    if categories:
        parts.append(categories)
    parts.extend([summary, link])
    return '\n'.join(parts)