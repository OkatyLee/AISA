"""
Paper Service - сервис для работы со статьями.

Использует облачную LLM (OpenRouter) для:
- Суммаризации статей
- Сравнения статей
- Генерации PDF-отчётов
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from io import BytesIO

from .client import OpenRouterClient, ChatMessage, LLMResponse
from utils.logger import setup_logger

logger = setup_logger(name="paper_service", level=logging.INFO)


class PaperService:
    """
    Сервис для анализа научных статей.
    """
    
    def __init__(self):
        self.llm = OpenRouterClient()
        
    async def close(self):
        await self.llm.close()
    
    async def summarize(
        self,
        paper: Dict[str, Any],
        detailed: bool = False,
    ) -> str:
        """
        Суммаризация статьи.
        
        Args:
            paper: Словарь с данными статьи (title, authors, abstract, text)
            detailed: Делать ли подробный анализ
            
        Returns:
            Текст суммаризации
        """
        system_prompt = """Ты эксперт по анализу научных статей. 
Твоя задача - провести анализ статьи на русском языке.

Структура анализа:
1. **Основная тема и цель** — о чём статья и какую проблему решает
2. **Методология** — какие методы и подходы используются
3. **Ключевые результаты** — главные выводы и достижения
4. **Практическое значение** — как это можно применить

Требования:
- Используй научную терминологию, но объясняй сложные концепции простым языком
- Выделяй самые важные моменты
- Сохраняй объективность и точность
- Если текст статьи неполный, опирайся на аннотацию
- Для математических формул используй LaTeX: $E = mc^2$
- Не выдумывай факты — работай только с предоставленной информацией"""

        # Формируем контент статьи
        content_parts = []
        
        if paper.get("title"):
            content_parts.append(f"**Название:** {paper['title']}")
            
        if paper.get("authors"):
            authors = paper["authors"]
            if isinstance(authors, list):
                authors = ", ".join(authors)
            content_parts.append(f"**Авторы:** {authors}")
            
        if paper.get("year"):
            content_parts.append(f"**Год:** {paper['year']}")
            
        if paper.get("journal"):
            content_parts.append(f"**Журнал:** {paper['journal']}")
            
        if paper.get("abstract"):
            content_parts.append(f"**Аннотация:**\n{paper['abstract']}")
            
        if paper.get("text"):
            # Ограничиваем длину текста
            text = paper["text"][:30000] if len(paper.get("text", "")) > 30000 else paper["text"]
            content_parts.append(f"**Полный текст:**\n{text}")
        
        user_prompt = "Проанализируй следующую научную статью:\n\n" + "\n\n".join(content_parts)
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        
        try:
            response = await self.llm.chat(
                messages,
                temperature=0.3,
                max_tokens=4096 if detailed else 2048,
            )
            return response.content
        except Exception as e:
            logger.error(f"Ошибка при суммаризации: {e}")
            raise
    
    async def compare(
        self,
        papers: List[Dict[str, Any]],
    ) -> str:
        """
        Сравнение нескольких статей.
        
        Args:
            papers: Список статей для сравнения
            
        Returns:
            Текст сравнительного анализа
        """
        if len(papers) < 2:
            return "Для сравнения нужно минимум 2 статьи."
        
        system_prompt = """Ты эксперт по сравнительному анализу научных статей.

Сравни предоставленные статьи и подготовь структурированный анализ:

1. **Краткие тезисы каждой статьи** (2-3 ключевых пункта)
2. **Сравнение подходов** — цели, методология, данные
3. **Сильные и слабые стороны** каждой работы
4. **Практические рекомендации** — когда какую работу использовать
5. **Общий вывод** — какая статья более релевантна для какой задачи

Требования:
- Будь объективен и точен
- Не выдумывай факты
- Используй LaTeX для формул
- Отвечай на русском языке"""

        # Суммаризируем каждую статью параллельно
        summaries = await asyncio.gather(
            *[self.summarize(paper, detailed=False) for paper in papers],
            return_exceptions=True
        )
        
        # Формируем контент для сравнения
        chunks = []
        for i, (paper, summary) in enumerate(zip(papers, summaries), 1):
            title = paper.get("title", f"Статья {i}")
            authors = paper.get("authors", [])
            if isinstance(authors, list):
                authors = ", ".join(authors)
            year = paper.get("year", "")
            
            chunk = f"**[{i}] {title}** ({year})\n"
            chunk += f"Авторы: {authors}\n"
            
            if isinstance(summary, Exception):
                chunk += f"Ошибка при анализе: {summary}\n"
            else:
                chunk += f"Анализ:\n{summary}\n"
                
            chunks.append(chunk)
        
        user_prompt = "Сравни следующие статьи:\n\n" + "\n---\n\n".join(chunks)
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        
        try:
            response = await self.llm.chat(
                messages,
                temperature=0.3,
                max_tokens=6000,
            )
            return response.content
        except Exception as e:
            logger.error(f"Ошибка при сравнении: {e}")
            raise
    
    async def explain(
        self,
        question: str,
        paper: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Объяснить концепцию, возможно в контексте статьи.
        
        Args:
            question: Вопрос пользователя
            paper: Статья для контекста (опционально)
            
        Returns:
            Объяснение
        """
        system_prompt = """Ты научный эксперт и педагог. Объясняй сложные концепции простым языком.

Правила:
- Используй аналогии и примеры
- Структурируй объяснение (от простого к сложному)
- Если есть контекст статьи — опирайся на него
- Используй LaTeX для формул
- Отвечай на русском языке"""

        user_prompt = question
        
        if paper:
            context = f"\n\nКонтекст (статья):\n"
            context += f"Название: {paper.get('title', 'Неизвестно')}\n"
            if paper.get("abstract"):
                context += f"Аннотация: {paper['abstract'][:2000]}\n"
            user_prompt = question + context
        
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        
        try:
            response = await self.llm.chat(
                messages,
                temperature=0.5,
                max_tokens=2048,
            )
            return response.content
        except Exception as e:
            logger.error(f"Ошибка при объяснении: {e}")
            raise
    
    async def generate_pdf_report(
        self,
        content: str,
        title: str = "Анализ статьи",
    ) -> BytesIO:
        """
        Генерация PDF-отчёта из markdown-текста.
        
        Args:
            content: Markdown-контент
            title: Заголовок отчёта
            
        Returns:
            BytesIO с PDF-файлом
        """
        try:
            import fitz  # PyMuPDF
            
            # Создаём PDF документ
            doc = fitz.open()
            
            # Настройки страницы
            page_width = 595  # A4
            page_height = 842
            margin = 50
            
            # Создаём первую страницу
            page = doc.new_page(width=page_width, height=page_height)
            
            # Шрифты
            fontsize_title = 16
            fontsize_body = 11
            line_height = fontsize_body * 1.4
            
            # Позиция курсора
            y = margin
            
            # Заголовок
            page.insert_text(
                (margin, y + fontsize_title),
                title,
                fontsize=fontsize_title,
                fontname="helv",
            )
            y += fontsize_title * 2
            
            # Разделяем контент на строки
            lines = content.split("\n")
            
            for line in lines:
                # Проверяем, нужна ли новая страница
                if y > page_height - margin:
                    page = doc.new_page(width=page_width, height=page_height)
                    y = margin
                
                # Обрабатываем markdown заголовки
                if line.startswith("# "):
                    page.insert_text(
                        (margin, y + fontsize_title),
                        line[2:],
                        fontsize=fontsize_title,
                    )
                    y += fontsize_title * 1.5
                elif line.startswith("## "):
                    page.insert_text(
                        (margin, y + fontsize_body + 2),
                        line[3:],
                        fontsize=fontsize_body + 2,
                    )
                    y += (fontsize_body + 2) * 1.5
                elif line.startswith("**") and line.endswith("**"):
                    page.insert_text(
                        (margin, y + fontsize_body),
                        line[2:-2],
                        fontsize=fontsize_body,
                    )
                    y += line_height
                elif line.strip():
                    # Обычный текст — разбиваем на строки по ширине
                    max_chars = int((page_width - 2 * margin) / (fontsize_body * 0.5))
                    words = line.split()
                    current_line = ""
                    
                    for word in words:
                        if len(current_line) + len(word) + 1 <= max_chars:
                            current_line += (" " if current_line else "") + word
                        else:
                            if current_line:
                                page.insert_text(
                                    (margin, y + fontsize_body),
                                    current_line,
                                    fontsize=fontsize_body,
                                )
                                y += line_height
                                
                                if y > page_height - margin:
                                    page = doc.new_page(width=page_width, height=page_height)
                                    y = margin
                            current_line = word
                    
                    if current_line:
                        page.insert_text(
                            (margin, y + fontsize_body),
                            current_line,
                            fontsize=fontsize_body,
                        )
                        y += line_height
                else:
                    y += line_height * 0.5  # Пустая строка
            
            # Сохраняем в BytesIO
            pdf_bytes = BytesIO()
            pdf_bytes.write(doc.tobytes())
            pdf_bytes.seek(0)
            doc.close()
            
            return pdf_bytes
            
        except Exception as e:
            logger.error(f"Ошибка при генерации PDF: {e}")
            raise
