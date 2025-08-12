from config import load_config
from services.utils.paper import Paper
from utils.logger import setup_logger
import logging
from openai import AsyncOpenAI
from config.constants import LLM_API_BASE_URL


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
                
                Резюме должно быть понятным для широкой аудитории, но сохранять научную точность."""
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
                model="tngtech/deepseek-r1t2-chimera:free",
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