from datetime import datetime
import sqlite3
import hashlib
from typing import Dict, Any, List, Tuple
import json
from utils import setup_logger

logger = setup_logger(name="db_manager_logger", log_file="logs/db_manager.log", level="INFO")

class DatabaseManager:
    def __init__(self, db_path: str = 'db/scientific_assistant.db'):
        self.db_path = db_path
        self.init_database()
        
    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Основная таблица для сохраненных публикаций
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS saved_publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    external_id TEXT,
                    source TEXT DEFAULT 'unknown',
                    title TEXT NOT NULL,
                    authors TEXT,
                    url TEXT NOT NULL,
                    abstract TEXT,
                    doi TEXT,
                    journal TEXT,
                    publication_date TEXT,
                    keywords TEXT,
                    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tags TEXT, 
                    notes TEXT,
                    categories TEXT,
                    source_metadata TEXT,
                    UNIQUE (user_id, url)
                )
            ''')
            
            # Таблица для тегов (для будущего расширения)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для связи публикаций и тегов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS publication_tags (
                    publication_id INTEGER,
                    tag_id INTEGER,
                    PRIMARY KEY (publication_id, tag_id),
                    FOREIGN KEY (publication_id) REFERENCES saved_publications(id),
                    FOREIGN KEY (tag_id) REFERENCES tags(id)
                )
            ''')
            
            # Индексы для производительности
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON saved_publications(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_external_id ON saved_publications(external_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON saved_publications(source)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_saved_at ON saved_publications(saved_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_doi ON saved_publications(doi)')
            
            # Уникальный индекс для предотвращения дублирования
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_user_paper 
                ON saved_publications(user_id, url)
            ''')
            
            conn.commit()
    
    def _generate_paper_id(self, paper: Dict[str, Any]) -> str:
        """Генерация уникального ID для статьи на основе URL"""
        return hashlib.md5(paper['url'].encode()).hexdigest()

    async def save_paper(self, user_id: int, paper: Dict[str, Any]) -> bool:

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT id FROM saved_publications
                    WHERE user_id = ? AND external_id = ?
                    ''', (user_id, paper['external_id'])
                )
                if cursor.fetchone():
                    return False
                pub_date = paper.get('publication_date', paper.get('published_date', ''))
                if isinstance(pub_date, datetime):
                    pub_date = pub_date.date().isoformat()
                cursor.execute(
                    '''
                    INSERT INTO saved_publications (
                        user_id, external_id, source, title, authors, url, abstract, doi, 
                        journal, publication_date, keywords, tags, categories, source_metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        user_id, 
                        paper.get('external_id', ''), 
                        paper.get('source', 'unknown'),
                        paper.get('title', ''), 
                        ', '.join(paper.get('authors', [])), 
                        paper.get('url', ''), 
                        paper.get('abstract', ''), 
                        paper.get('doi', ''),
                        paper.get('journal', ''),
                        pub_date,
                        ', '.join(paper.get('keywords', [])),
                        ', '.join(paper.get('tags', [])),
                        ', '.join(paper.get('categories', [])),
                        json.dumps(paper.get('source_metadata', {}))
                    )
                )
                
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"Ошибка при сохранении статьи: {e}")
            return False
        
    async def get_user_library(self, user_id: int, limit: int = 50, offset: int = 0,
                            sort_by: str = "saved_at", order: str = "DESC") -> List[Dict[str, Any]]:
        '''
        Получение библиотеки пользователя с пагинацией и сортировкой
        :param user_id: ID пользователя
        :param limit: Максимальное количество результатов
        :param offset: Смещение для пагинации
        :param sort_by: Поле для сортировки
        :param order: Порядок сортировки (ASC или DESC)
        :return: Список статей пользователя
        Форматирование:
        {
            "id": int,
            "user_id": int,
            "arxiv_id": str,
            "title": str,
            "authors": list[str],
            "url": str,
            "abstract": str,
            "publication_date": str,
            "saved_at": str,
            "tags": list[str],
            "notes": str,
            "categories": list[str]
        }
        '''
        valid_sort_fields = ["saved_at", "title", "publication_date"]
        
        if sort_by not in valid_sort_fields:
            sort_by = "saved_at"
            
        if order not in ["ASC", "DESC"]:
            order = "DESC"
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f'''
                    SELECT * FROM saved_publications
                    WHERE user_id = ?
                    ORDER BY {sort_by} {order}
                    LIMIT ? OFFSET ?
                    ''', (user_id, limit, offset)
                )
                rows = cursor.fetchall()
                library = []
                for row in rows:
                    paper = {
                        'id': row[0],
                        'user_id': row[1],
                        'external_id': row[2],
                        'source': row[3],
                        'title': row[4],
                        'authors': row[5].split(', ') if row[5] else [],
                        'url': row[6],
                        'abstract': row[7],
                        'doi': row[8],
                        'journal': row[9],
                        'publication_date': row[10],
                        'keywords': row[11].split(', ') if row[11] else [],
                        'saved_at': row[12],
                        'tags': row[13].split(', ') if row[13] else [],
                        'notes': row[14],
                        'categories': row[15].split(', ') if row[15] else [],
                        'source_metadata': json.loads(row[16]) if row[16] else {},
                        # Поддержка обратной совместимости
                        'arxiv_id': row[2] if row[3] == 'arxiv' else '',
                        'published_date': row[10]  # Alias для совместимости
                    }
                    library.append(paper)
                return library
        except Exception as e:
            logger.error(f"Ошибка при получении сохраненных статей: {e}")
            return []
        
    async def search_in_library(self, user_id: int, query: str) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                search_query = f"%{query}%"
                
                cursor.execute('''
                    SELECT * FROM saved_publications
                    WHERE user_id = ? AND (
                        title LIKE ? OR
                        authors LIKE ? OR
                        abstract LIKE ? OR
                        keywords LIKE ? OR
                        tags LIKE ? OR
                        notes LIKE ? OR
                        categories LIKE ?
                    )
                    ORDER BY saved_at DESC
                ''', (user_id, search_query, search_query, search_query, search_query, search_query, search_query, search_query))
                
                papers = [dict(row) for row in cursor.fetchall()]
                return papers
        except Exception as e:
            logger.error(f"Ошибка при поиске в библиотеке: {e}")
            return []
        
    async def delete_paper(self, user_id: int, paper_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    DELETE FROM saved_publications
                    WHERE external_id = ? AND user_id = ?
                    ''', (paper_id, user_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при удалении статьи: {e}")
            return False
        
    async def is_paper_saved(self, user_id: int, paper_url: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT 1 FROM saved_publications
                    WHERE user_id = ? AND url = ?
                    ''', (user_id, paper_url)
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Ошибка при проверке сохраненной статьи: {e}")
            return False
        
    async def get_library_status(self, user_id: int) -> Dict[str, Any]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Получение общего количества сохраненных статей
                cursor.execute(
                    '''
                    SELECT COUNT(*) FROM saved_publications
                    WHERE user_id = ?
                    ''', (user_id,)
                )
                total_count = cursor.fetchone()[0]
                
                # Получение количества статей, сохраненных за последние 30 дней
                cursor.execute('''
                    SELECT COUNT(*) FROM saved_publications 
                    WHERE user_id = ? AND saved_at > datetime('now', '-30 days')
                ''', (user_id,))
                recent_count = cursor.fetchone()[0]

                def fetch_popular_content_by_field(field: str) -> List[Tuple[str, int]]:
                    cursor.execute(f'''
                        SELECT {field} FROM saved_publications
                        WHERE user_id = ? AND {field} IS NOT NULL
                    ''', (user_id,))
    
                
                    all_vals = []
                    for row in cursor.fetchall():
                        field_str = row[0] if row[0] else ""
                        if field_str:
                            # Теги сохранены как строка через запятую
                            fields = field_str.split(', ')
                            all_vals.extend(fields)

                    # Подсчет популярности тегов
                    field_counts = {}
                    for field in all_vals:
                        field_counts[field] = field_counts.get(field, 0) + 1

                    popular_fields = sorted(field_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                    return popular_fields
                
                popular_tags = fetch_popular_content_by_field('tags')
                
                popular_authors = fetch_popular_content_by_field('authors')
                return {
                    'total_papers': total_count,
                    'recent_papers': recent_count,
                    'popular_tags': popular_tags,
                    'popular_authors': popular_authors
                }

        except Exception as e:
            logger.error(f"Ошибка при получении статуса библиотеки: {e}")
            return {'total_papers': 0, 'recent_papers': 0, 'popular_tags': [], 'popular_authors': []}
        
    async def add_note_to_paper(self, user_id: int, paper_id: int, note: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    UPDATE saved_publications
                    SET notes = ?
                    WHERE id = ? AND user_id = ?
                    ''', (note, paper_id, user_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при добавлении заметки к статье: {e}")
            return False
        
    async def export_library_bibtex(self, user_id: int) -> str:
        library = await self.get_user_library(user_id, limit=1000)
        if not library:
            logger.warning("Библиотека пользователя пуста")
            return ""

        bibtex_entries = []
        for paper in library:
            title = paper.get("title", "Без названия")
            authors = paper.get("authors", [])
            url = paper.get("url", "")
            publication_date = paper.get("publication_date", "")
            doi = paper.get("doi", "")
            journal = paper.get("journal", "")
            source = paper.get("source", "unknown")
            external_id = paper.get("external_id", "")

            # Обработка авторов
            if isinstance(authors, list):
                authors_list = authors
            else:
                authors_list = authors.split(', ') if authors else []
            author_str = ' and '.join(authors_list)

            # Определяем тип записи на основе источника
            entry_type = "article"
            if source == "arxiv":
                entry_type = "misc"  # Препринты обычно misc
            elif journal:
                entry_type = "article"

            # Формируем BibTeX запись
            entry = f"""@{entry_type}{{{paper['id']},
    title = {{{title}}},
    author = {{{author_str}}},
    year = {{{publication_date[:4] if publication_date else ""}}}"""

            if journal:
                entry += f",\n    journal = {{{journal}}}"
            
            if doi:
                entry += f",\n    doi = {{{doi}}}"
            
            if url:
                entry += f",\n    url = {{{url}}}"
            
            if external_id and source:
                if source == "arxiv":
                    entry += f",\n    eprint = {{{external_id}}},\n    archivePrefix = {{arXiv}}"
                else:
                    entry += f",\n    note = {{{source.upper()} ID: {external_id}}}"
            
            entry += f",\n    note = {{Saved from AISA - {source.upper()}}}\n}}"
            bibtex_entries.append(entry)

        return "\n\n".join(bibtex_entries)

    async def delete_paper_by_external_id(self, user_id: int, external_id: str, source: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    DELETE FROM saved_publications
                    WHERE user_id = ? AND external_id = ? AND source = ?
                    ''', (user_id, external_id, source)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при удалении статьи по внешнему ID: {e}")
            return False
        
    async def delete_paper_by_url_part(self, user_id: int, url_part: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    DELETE FROM saved_publications
                    WHERE user_id = ? AND url LIKE ?
                    ''', (user_id, f'%{url_part}%')
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при удалении статьи по части URL: {e}")
            return False

    async def delete_paper_by_title_hash(self, user_id: int, title_hash: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Получаем все заголовки статей пользователя
                titles = cursor.execute(
                    '''
                    SELECT id, title FROM saved_publications
                    WHERE user_id = ?
                    ''', (user_id,)
                ).fetchall()
                
                if not titles:
                    return False
                
                for paper_id, title in titles:
                    if hashlib.sha256(title.encode()).hexdigest() == title_hash:
                        cursor.execute(
                            '''
                            DELETE FROM saved_publications
                            WHERE id = ? AND user_id = ? AND title = ?
                            ''', (paper_id, user_id, title)
                        )
                        conn.commit()
                        return cursor.rowcount > 0
                        
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при удалении статьи по хешу заголовка: {e}")
            return False

    async def get_paper_by_title_hash(self, user_id: int, title_hash: str) -> Dict[str, Any]:
        """
        Получает статью из библиотеки пользователя по хешу заголовка.
        
        Args:
            user_id: ID пользователя
            title_hash: Хеш заголовка статьи
            
        Returns:
            Словарь с данными статьи или None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    SELECT id, external_id, source, title, authors, url, abstract, 
                           doi, journal, publication_date, keywords, saved_at, 
                           tags, notes, categories, source_metadata
                    FROM saved_publications
                    WHERE user_id = ?
                    ''', (user_id,)
                )
                
                papers = cursor.fetchall()
                for paper in papers:
                    # Проверяем хеш заголовка
                    if hashlib.sha256(paper[3].encode()).hexdigest() == title_hash:
                        return {
                            "id": paper[0],
                            "external_id": paper[1],
                            "source": paper[2] or 'unknown',
                            "title": paper[3],
                            "authors": json.loads(paper[4]) if paper[4] else [],
                            "url": paper[5],
                            "abstract": paper[6] or '',
                            "doi": paper[7] or '',
                            "journal": paper[8] or '',
                            "publication_date": paper[9] or '',
                            "keywords": json.loads(paper[10]) if paper[10] else [],
                            "saved_at": paper[11],
                            "tags": json.loads(paper[12]) if paper[12] else [],
                            "notes": paper[13] or '',
                            "categories": json.loads(paper[14]) if paper[14] else [],
                            "source_metadata": json.loads(paper[15]) if paper[15] else {}
                        }
                        
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении статьи по хешу заголовка: {e}")
            return None
        
    async def edit_paper_tags(self, user_id: int, paper_id: str, new_tags: str) -> bool:
        """
        Изменяет теги статьи пользователя.
        
        Args:
            user_id: ID пользователя
            paper_id: ID статьи
            new_tags: Новые теги в виде строки, разделенные запятыми
            
        Returns:
            True, если теги успешно изменены, иначе False
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    UPDATE saved_publications
                    SET tags = ?, categories = ?
                    WHERE external_id = ? AND user_id = ?
                    ''', (new_tags, new_tags, paper_id, user_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при изменении тегов статьи: {e}")
            return False
