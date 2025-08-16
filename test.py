import sqlite3
from sympy import im
import test
from utils.report import _pdf_from_markdown_to_path
import os
def test_markdown_to_pdf():
    """Тестовая функция с диагностикой"""
    
    # Тестовый контент
    markdown_content = """
# Тестовый документ

Это тестовый документ с формулой: $E = mc^2$

## Блочная формула

$$\\int_{0}^{\\infty} e^{-x} dx = 1$$

## Обычный текст

Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
"""
    
    # Проверим текущую директорию
    current_dir = os.getcwd()
    print(f"Текущая директория: {current_dir}")
    
    # Тестируем разные варианты путей
    test_paths = [
        "test_output.pdf",  # В текущей директории
        "./test_output.pdf",  # Явно в текущей директории  
        os.path.join(current_dir, "test_output.pdf"),  # Абсолютный путь
    ]
    
    for test_path in test_paths:
        print(f"\n--- Тестируем путь: {test_path} ---")
        result = _pdf_from_markdown_to_path(markdown_content, test_path)
        print(f"Результат: {result}")
        
        if result == "success":
            print("✅ Успешно!")
            break
        else:
            print("❌ Ошибка")

from database import SQLDatabase as db
with sqlite3.connect(db.db_path) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM saved_publications")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
