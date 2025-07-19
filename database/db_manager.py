import sqlite3
import hashlib
from typing import Dict, Any, List
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
                    arxiv_id TEXT,
                    title TEXT NOT NULL,
                    authors TEXT,
                    url TEXT NOT NULL,
                    abstract TEXT,
                    published_date TEXT,
                    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tags TEXT, 
                    notes TEXT,
                    categories TEXT,
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
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_arxiv_id ON saved_publications(arxiv_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_saved_at ON saved_publications(saved_at)')
            
            # Уникальный индекс для предотвращения дублирования
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_user_paper 
                ON saved_publications(user_id, url)
            ''')
            
            conn.commit()
    
    def _generate_paper_id(self, paper: Dict[str, Any]) -> str:
        """Генерация уникального ID для статьи на основе URL"""
        return hashlib.md5(paper['url'].encode()).hexdigest()
    
    async def save_paper(self, user_id: int, paper: Dict[str, Any], tags: List[str] = None) -> bool:
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    '''
                    SELECT id FROM saved_publications
                    WHERE user_id = ? AND url = ?
                    ''', (user_id, paper['url'])
                )
                
                if cursor.fetchone():
                    return False

                cursor.execute(
                    '''
                    INSERT INTO saved_publications (user_id, arxiv_id, title, authors, url, abstract, published_date, tags, categories)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (user_id, 
                          paper['arxiv_id'], 
                          paper['title'], 
                          ', '.join(paper['authors']), 
                          paper['url'], paper['abstract'], 
                          paper['published_date'], 
                          ', '.join(tags) if tags else '',
                          ', '.join(paper.get('categories', ['']))  
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
        
        valid_sort_fields = ["saved_at", "title", "published_date"]
        
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
                        'arxiv_id': row[2],
                        'title': row[3],
                        'authors': row[4].split(', ') if row[4] else [],
                        'url': row[5],
                        'abstract': row[6],
                        'published_date': row[7],
                        'saved_at': row[8],
                        'tags': json.loads(row[9]) if row[9] else [],
                        'notes': row[10],
                        'categories': row[11].split(', ') if row[11] else []
                    }
                    paper['tags'] = json.loads(paper['tags']) if paper['tags'] else []
                    library.append(paper)
                return library
        except Exception as e:
            logger.error(f"Ошибка при получении сохраненных статей: {e}")
            return []
        
    async def search_in_library(self, user_id: int, query: str) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                conn.row_factory = sqlite3.Row
                cursor.execute(
                    '''
                    SELECT * FROM saved_publications
                    WHERE user_id = ? AND (
                        title LIKE ? OR authors LIKE ? 
                        OR abstract LIKE ? OR tags LIKE ?)
                    ORDER BY saved_at DESC
                    ''', (user_id, f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%')
                )
                rows = cursor.fetchall()
                library = []
                for row in rows:
                    paper = dict(row)
                    paper['tags'] = json.loads(paper['tags']) if paper['tags'] else []
                    library.append(paper)
                return library
        except Exception as e:
            logger.error(f"Ошибка при поиске в библиотеке: {e}")
            return []
        
    async def delete_paper(self, user_id: int, paper_id: int) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    DELETE FROM saved_publications
                    WHERE id = ? AND user_id = ?
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
                
                # Получение популярных тегов
                cursor.execute('''
                    SELECT tags FROM saved_publications 
                    WHERE user_id = ? AND tags IS NOT NULL
                ''', (user_id,))
                
                all_tags = []
                for row in cursor.fetchall():
                    tags = json.loads(row[0]) if row[0] else []
                    all_tags.extend(tags)
                
                # Подсчет популярности тегов
                tag_counts = {}
                for tag in all_tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
                
                popular_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                
                return {
                    'total_papers': total_count,
                    'recent_papers': recent_count,
                    'popular_tags': popular_tags
                }

        except Exception as e:
            logger.error(f"Ошибка при получении статуса библиотеки: {e}")
            return {'total_papers': 0, 'recent_papers': 0, 'popular_tags': []}
        
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
            published_date = paper.get("published_date", "")

            authors_list = authors.split(', ') if authors else []
            author_str = ' and '.join(authors_list)

            entry = f"""
            @article{{{paper['id']}
                title = {{{title}}}
                author = {{{author_str}}}
                url = {{{url}}}
                year = {{{published_date}}}
                note = {{{'Saved from AISA'}}}
                }}
            """
            bibtex_entries.append(entry)

        return "\n\n".join(bibtex_entries)
    