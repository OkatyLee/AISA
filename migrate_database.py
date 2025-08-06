#!/usr/bin/env python3
"""
Скрипт миграции базы данных для обновления схемы saved_publications.
Добавляет новые поля в соответствии с текущей реализацией Paper класса.
"""
import sqlite3
import json
import sys
import os
from typing import Dict, Any

# Добавляем корневую папку проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger

logger = setup_logger(name="migration_logger", log_file="logs/migration.log", level="INFO")

def backup_database(db_path: str) -> str:
    """Создает резервную копию базы данных."""
    import shutil
    backup_path = f"{db_path}.backup"
    shutil.copy2(db_path, backup_path)
    logger.info(f"Резервная копия создана: {backup_path}")
    return backup_path

def check_table_structure(db_path: str) -> Dict[str, Any]:
    """Проверяет текущую структуру таблицы saved_publications."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Получаем информацию о таблице
        cursor.execute("PRAGMA table_info(saved_publications)")
        columns = cursor.fetchall()
        
        column_names = [col[1] for col in columns]
        logger.info(f"Текущие колонки таблицы: {column_names}")
        
        # Проверяем наличие данных
        cursor.execute("SELECT COUNT(*) FROM saved_publications")
        count = cursor.fetchone()[0]
        logger.info(f"Количество записей в таблице: {count}")
        
        return {
            'columns': column_names,
            'count': count,
            'needs_migration': not all(col in column_names for col in [
                'external_id', 'source', 'doi', 'journal', 'keywords', 'source_metadata'
            ])
        }

def migrate_database(db_path: str):
    """Выполняет миграцию базы данных."""
    logger.info("Начинаем миграцию базы данных...")
    
    # Проверяем текущую структуру
    structure_info = check_table_structure(db_path)
    
    if not structure_info['needs_migration']:
        logger.info("База данных уже обновлена, миграция не требуется.")
        return True
    
    # Создаем резервную копию
    backup_database(db_path)
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        try:
            # Создаем новую таблицу с обновленной структурой
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS saved_publications_new (
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
            
            # Переносим данные из старой таблицы в новую
            logger.info("Переносим данные из старой таблицы в новую...")
            
            # Получаем все данные из старой таблицы
            cursor.execute("SELECT * FROM saved_publications")
            old_rows = cursor.fetchall()
            
            # Получаем названия колонок старой таблицы
            cursor.execute("PRAGMA table_info(saved_publications)")
            old_columns = [col[1] for col in cursor.fetchall()]
            
            for row in old_rows:
                old_data = dict(zip(old_columns, row))
                
                # Подготавливаем данные для новой таблицы
                new_data = {
                    'user_id': old_data.get('user_id'),
                    'external_id': old_data.get('arxiv_id', old_data.get('external_id', '')),
                    'source': 'arxiv' if old_data.get('arxiv_id') else old_data.get('source', 'unknown'),
                    'title': old_data.get('title', ''),
                    'authors': old_data.get('authors', ''),
                    'url': old_data.get('url', ''),
                    'abstract': old_data.get('abstract', ''),
                    'doi': old_data.get('doi', ''),
                    'journal': old_data.get('journal', ''),
                    'publication_date': old_data.get('published_date', old_data.get('publication_date', '')),
                    'keywords': old_data.get('keywords', ''),
                    'saved_at': old_data.get('saved_at'),
                    'tags': old_data.get('tags', ''),
                    'notes': old_data.get('notes', ''),
                    'categories': old_data.get('categories', ''),
                    'source_metadata': old_data.get('source_metadata', '{}')
                }
                
                # Вставляем данные в новую таблицу
                cursor.execute('''
                    INSERT INTO saved_publications_new (
                        user_id, external_id, source, title, authors, url, abstract, doi,
                        journal, publication_date, keywords, saved_at, tags, notes, categories, source_metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    new_data['user_id'], new_data['external_id'], new_data['source'],
                    new_data['title'], new_data['authors'], new_data['url'], new_data['abstract'],
                    new_data['doi'], new_data['journal'], new_data['publication_date'],
                    new_data['keywords'], new_data['saved_at'], new_data['tags'],
                    new_data['notes'], new_data['categories'], new_data['source_metadata']
                ))
            
            # Удаляем старую таблицу и переименовываем новую
            cursor.execute("DROP TABLE saved_publications")
            cursor.execute("ALTER TABLE saved_publications_new RENAME TO saved_publications")
            
            # Создаем индексы
            logger.info("Создаем индексы...")
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON saved_publications(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_external_id ON saved_publications(external_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON saved_publications(source)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_saved_at ON saved_publications(saved_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_doi ON saved_publications(doi)')
            
            # Создаем уникальный индекс
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_user_paper 
                ON saved_publications(user_id, url)
            ''')
            
            conn.commit()
            logger.info(f"Миграция завершена успешно. Перенесено {len(old_rows)} записей.")
            
        except Exception as e:
            logger.error(f"Ошибка при миграции: {e}")
            conn.rollback()
            return False
    
    # Проверяем результат миграции
    final_structure = check_table_structure(db_path)
    logger.info(f"Структура после миграции: {final_structure['columns']}")
    logger.info(f"Количество записей после миграции: {final_structure['count']}")
    
    return True

def main():
    """Основная функция миграции."""
    db_path = "db/scientific_assistant.db"
    
    if not os.path.exists(db_path):
        logger.error(f"База данных не найдена: {db_path}")
        return False
    
    print("=" * 60)
    print("МИГРАЦИЯ БАЗЫ ДАННЫХ СОХРАНЕННЫХ СТАТЕЙ")
    print("=" * 60)
    print(f"База данных: {db_path}")
    
    # Проверяем, нужна ли миграция
    structure_info = check_table_structure(db_path)
    
    if not structure_info['needs_migration']:
        print("✅ База данных уже обновлена, миграция не требуется.")
        return True
    
    print(f"📊 Найдено записей для миграции: {structure_info['count']}")
    print("🔄 Выполняем миграцию...")
    
    try:
        success = migrate_database(db_path)
        if success:
            print("✅ Миграция завершена успешно!")
            print("\n📋 Новые поля в таблице:")
            print("   - external_id: Универсальный внешний ID (ArXiv, IEEE, PubMed)")
            print("   - source: Источник статьи (arxiv, ieee, ncbi)")
            print("   - doi: DOI статьи")
            print("   - journal: Журнал публикации")
            print("   - publication_date: Дата публикации (вместо published_date)")
            print("   - keywords: Ключевые слова статьи")
            print("   - source_metadata: Метаданные источника (JSON)")
            print("\n🔧 Обратная совместимость:")
            print("   - Поле arxiv_id теперь заполняется из external_id для ArXiv статей")
            print("   - published_date остается доступным как алиас")
        else:
            print("❌ Ошибка при миграции базы данных.")
            return False
            
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        print(f"❌ Неожиданная ошибка: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("МИГРАЦИЯ ЗАВЕРШЕНА")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
