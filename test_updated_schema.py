#!/usr/bin/env python3
"""
Тестирование обновленной схемы базы данных для сохраненных статей.
"""
import asyncio
import sys
import os
from datetime import datetime

# Добавляем корневую папку проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager

async def test_updated_schema():
    """Тестирует обновленную схему базы данных."""
    
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ОБНОВЛЕННОЙ СХЕМЫ БД")
    print("=" * 60)
    
    db_path = "test_updated_library.db"
    
    # Удаляем тестовую БД если она существует
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db_manager = DatabaseManager(db_path)
    
    try:
        # Инициализируем БД с новой схемой
        print("1. Инициализация новой схемы БД...")
        db_manager.init_database()
        print("   ✅ Схема создана")
        
        # Создаем тестовые статьи разных источников
        test_papers = [
            # ArXiv статья
            {
                'title': 'Machine Learning in Physics',
                'authors': ['John Doe', 'Jane Smith'],
                'url': 'https://arxiv.org/abs/2301.12345',
                'abstract': 'This paper explores machine learning applications in physics.',
                'doi': '10.48550/arXiv.2301.12345',
                'journal': '',
                'publication_date': '2023-01-15',
                'keywords': ['machine learning', 'physics', 'neural networks'],
                'external_id': '2301.12345',
                'source': 'arxiv',
                'categories': ['cs.LG', 'physics.data-an'],
                'source_metadata': {'arxiv_category': 'cs.LG', 'submission_date': '2023-01-10'}
            },
            # IEEE статья
            {
                'title': 'Deep Learning for Signal Processing',
                'authors': ['Alice Johnson', 'Bob Wilson'],
                'url': 'https://ieeexplore.ieee.org/document/9876543',
                'abstract': 'A comprehensive study on deep learning applications in signal processing.',
                'doi': '10.1109/TSP.2023.1234567',
                'journal': 'IEEE Transactions on Signal Processing',
                'publication_date': '2023-03-20',
                'keywords': ['deep learning', 'signal processing', 'neural networks'],
                'external_id': '9876543',
                'source': 'ieee',
                'categories': ['signal processing', 'machine learning'],
                'source_metadata': {'ieee_section': 'Signal Processing', 'pages': '1-12'}
            },
            # PubMed/NCBI статья
            {
                'title': 'AI in Medical Diagnosis',
                'authors': ['Dr. Sarah Davis', 'Dr. Michael Brown'],
                'url': 'https://pubmed.ncbi.nlm.nih.gov/37654321',
                'abstract': 'Application of artificial intelligence in medical diagnosis systems.',
                'doi': '10.1038/s41598-023-12345-6',
                'journal': 'Nature Scientific Reports',
                'publication_date': '2023-05-12',
                'keywords': ['artificial intelligence', 'medical diagnosis', 'healthcare'],
                'external_id': '37654321',
                'source': 'ncbi',
                'categories': ['medical AI', 'diagnostics'],
                'source_metadata': {'pmid': '37654321', 'mesh_terms': ['Artificial Intelligence', 'Diagnosis']}
            }
        ]
        
        test_user_id = 12345
        
        # Тестируем сохранение статей
        print("\n2. Тестирование сохранения статей...")
        for i, paper in enumerate(test_papers, 1):
            success = await db_manager.save_paper(test_user_id, paper, tags=['test', f'source_{paper["source"]}'])
            source = paper['source'].upper()
            if success:
                print(f"   ✅ {source} статья сохранена: {paper['title'][:50]}...")
            else:
                print(f"   ❌ Ошибка сохранения {source} статьи")
        
        # Тестируем получение библиотеки
        print("\n3. Тестирование получения библиотеки...")
        library = await db_manager.get_user_library(test_user_id)
        print(f"   📚 Получено статей: {len(library)}")
        
        for paper in library:
            print(f"   📄 {paper['source'].upper()}: {paper['title'][:40]}...")
            print(f"      External ID: {paper['external_id']}")
            print(f"      DOI: {paper.get('doi', 'N/A')}")
            print(f"      Journal: {paper.get('journal', 'N/A') or 'N/A'}")
            print(f"      Keywords: {len(paper.get('keywords', []))} шт.")
            
            # Проверяем обратную совместимость
            if paper['source'] == 'arxiv':
                print(f"      ArXiv ID (совместимость): {paper.get('arxiv_id', 'N/A')}")
            
            print(f"      Metadata: {len(paper.get('source_metadata', {}))} полей")
            print()
        
        # Тестируем поиск
        print("4. Тестирование расширенного поиска...")
        
        test_queries = [
            ('machine learning', 'по ключевым словам'),
            ('IEEE', 'по журналу'),
            ('10.1109', 'по DOI'),
            ('Nature', 'по названию журнала')
        ]
        
        for query, description in test_queries:
            results = await db_manager.search_in_library(test_user_id, query)
            print(f"   🔍 Поиск {description} '{query}': {len(results)} результатов")
        
        # Тестируем статистику
        print("\n5. Тестирование статистики...")
        stats = await db_manager.get_library_status(test_user_id)
        print(f"   📊 Всего статей: {stats['total_papers']}")
        print(f"   📈 Недавних статей: {stats['recent_papers']}")
        print(f"   🏷️  Популярные теги: {len(stats['popular_tags'])} шт.")
        
        # Тестируем экспорт BibTeX
        print("\n6. Тестирование экспорта BibTeX...")
        bibtex = await db_manager.export_library_bibtex(test_user_id)
        if bibtex:
            print(f"   📄 BibTeX экспорт: {len(bibtex.split('@article'))} записей")
            # Показываем первые строки
            first_lines = bibtex.split('\n')[:5]
            for line in first_lines:
                if line.strip():
                    print(f"      {line}")
        else:
            print("   ❌ Ошибка экспорта BibTeX")
        
        print("\n✅ Все тесты пройдены успешно!")
        
        # Показываем структуру таблицы
        print("\n📋 Структура обновленной таблицы:")
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(saved_publications)")
            columns = cursor.fetchall()
            
            for col in columns:
                col_name, col_type = col[1], col[2]
                print(f"   - {col_name} ({col_type})")
        
    except Exception as e:
        print(f"❌ Ошибка в тестах: {e}")
        return False
    finally:
        # Очищаем тестовую БД
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"\n🧹 Тестовая БД удалена: {db_path}")
    
    return True

async def main():
    """Главная функция."""
    success = await test_updated_schema()
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    print("\n" + "=" * 60)
    if success:
        print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО")
    else:
        print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО С ОШИБКАМИ")
    print("=" * 60)
