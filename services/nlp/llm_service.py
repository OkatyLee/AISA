from unittest import result
from config import load_config
from services.utils.paper import Paper
from utils.logger import setup_logger
import logging
from openai import AsyncOpenAI, RateLimitError
from config.constants import LLM_API_BASE_URL
import asyncio


logger = setup_logger(
    name="llm_service_logger",
    level=logging.INFO
)

class LLMService:
    def __init__(self):
        """Инициализация LLM серивиса."""
        self.config = load_config()
        self.llm_client = None
        
    async def __aenter__(self):
        self.llm_client = AsyncOpenAI(
            base_url=LLM_API_BASE_URL,
            api_key=self.config.LLM_API_KEY,
            timeout=60.0,
            max_retries=3,
        )
        logger.info("LLMService инициализирован")
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        """Закрытие LLM клиента."""
        if self.llm_client:
            try:
                await self.llm_client.close()
                logger.info("LLMService закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии LLMService: {e}")
        return False  
    
    async def summarize(self, paper: str) -> str:
        """Генерация резюме с использованием LLM клиента."""
        try:
            system_prompt = """Ты эксперт по анализу научных статей. 
                Твоя задача - провести анализ статьи на русском языке.
                
                Структура анализа должна включать:
                1. Основную тему и цель исследования
                2. Ключевые методы или подходы
                3. Главные результаты и выводы
                4. Практическое значение работы
                
                Требования:
                - Используй научную терминологию, но объясняй сложные концепции
                - Выделяй самые важные моменты
                - Сохраняй объективность и точность
                - Если у статьи короткая аннотация, суммируй аккуратно без выдумывания деталей

                Резюме должно быть понятным для широкой аудитории, но сохранять научную точность. Используй примеры и аналогии для объяснения сложных идей.
                Для отображения математических формул используй LaTeX, например: $E = mc^2$.
                """
            #paper = paper.to_dict() if isinstance(paper, Paper) else paper
            #if not isinstance(paper, dict):
            #    raise ValueError("Неверный формат статьи для суммаризации")
            #abstract_text = paper.get('abstract', '') or ''
            #title_text = paper.get('title', 'Название статьи не указано')
            #authors_list = paper.get('authors', []) or []
            user_prompt = f"""Пожалуйста, проведи анализ следующей научной статьи:
                {paper}
            """
            completion = await self.llm_client.chat.completions.create(
                model="z-ai/glm-4.5-air:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=20000,
                temperature=0.3
            )

            return completion.choices[0].message.content
        except Exception as e:
            raise Exception(f"Ошибка при суммаризации статьи: {e}") from e

    async def compare_many(self, items: list[dict]) -> str:
        """Сравнение и сводная суммаризация нескольких статей.

        items: список словарей, полученных из fetch_full_texts_for_papers
        (title, authors, year, journal, url, source, doi, id, abstract, text)
        """
        # --- Делаем анализ статей ---
        tasks = []
        for paper in items:
            task = asyncio.create_task(
                self.summarize(paper.get('text', '')),
                name=f"summarize_{paper.get('id', 'unknown')}"
            )
            tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res, item in zip(results, items):
            if isinstance(res, Exception):
                # Обработка ошибки
                error_message = f"Ошибка при суммаризации статьи {item.get('id', 'unknown')}: {res}"
                logger.error(error_message)
                continue
            item['text'] = res
        try:
            system_prompt = (
                "Ты эксперт по сравнению научных статей. Сравни несколько работ и сделай выводы. "
                "Дай структурированный ответ на русском языке с разделами: \n"
                "1) Краткие тезисы каждой статьи (1-3 пункта)\n"
                "2) Сравнение целей, методологии, данных и результатов\n"
                "3) Сильные и слабые стороны каждой работы\n"
                "4) Практические выводы и рекомендации (когда какую работу использовать)\n"
                "5) Общий вывод и будущие направления\n"
                "Не выдумывай факты; если нет полного текста, опирайся на аннотацию."
                "Форматирование: markdown с LaTeX для формул. Не используй в ответах emoji\n"
            )

            # Собираем краткий контент
            chunks = []
            for i, it in enumerate(items, 1):
                title = it.get('title') or f"Статья {i}"
                authors = ", ".join(it.get('authors') or [])
                year = it.get('year') or ''
                journal = it.get('journal') or ''
                url = it.get('url') or ''
                abstract = (it.get('abstract') or '')[:2000]
                text = (it.get('text') or '')[:20000]
                chunk = (
                    f"— [{i}] {title} ({year}) {journal}\n"
                    f"Авторы: {authors}\n"
                    f"URL: {url}\n"
                    f"Аннотация: {abstract}\n"
                    f"Текст: {text}\n"
                )
                chunks.append(chunk)

            user_prompt = (
                "Сравни следующие статьи и подготовь сводку и рекомендации:\n\n" + "\n\n".join(chunks)
            )

            completion = await self.llm_client.chat.completions.create(
                model="z-ai/glm-4.5-air:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=20000,
                temperature=0.3,
            )
            return completion.choices[0].message.content
        except RateLimitError as e:
            # Этот блок выполнится только при ошибке 429 (Rate Limit Exceeded)
            logger.error(f"Достигнут лимит запросов. Детали ошибки: {e}")
            return "Лимит запросов на день исчерпан. Пожалуйста, попробуйте позже."
        except Exception as e:
            raise Exception(f"Ошибка при сравнительном анализе статей: {e}") from e