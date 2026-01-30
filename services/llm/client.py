"""
LLM Clients - унифицированный интерфейс для работы с LLM.

Поддерживает:
- Ollama (локальная LLM для NLU и чата)
- OpenRouter (облачная LLM для тяжёлых задач)
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncIterator
from dataclasses import dataclass
import httpx
from openai import AsyncOpenAI

from config import load_config
from utils.logger import setup_logger

logger = setup_logger(name="llm_client", level=logging.INFO)


@dataclass
class ChatMessage:
    """Сообщение в чате."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Ответ от LLM."""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None


class LLMClient(ABC):
    """Абстрактный базовый класс для LLM клиентов."""
    
    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Отправить запрос в чат."""
        pass
    
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Отправить запрос в чат со стримингом."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Проверить доступность сервиса."""
        pass


class OllamaClient(LLMClient):
    """
    Клиент для локальной LLM через Ollama.
    
    Используется для:
    - Классификации намерений
    - Извлечения сущностей
    - Обычного чата
    """
    
    DEFAULT_MODEL = "qwen2.5:3b"
    
    def __init__(
        self,
        base_url: str = "http://ollama:11434",
        model: str = None,
        timeout: float = 60.0
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout)
            )
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def is_available(self) -> bool:
        """Проверить доступность Ollama."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama недоступна: {e}")
            return False
    
    async def ensure_model(self) -> bool:
        """Убедиться, что модель загружена."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                
                # Проверяем, есть ли наша модель
                if not any(self.model in name for name in model_names):
                    logger.info(f"Загрузка модели {self.model}...")
                    pull_response = await client.post(
                        "/api/pull",
                        json={"name": self.model},
                        timeout=httpx.Timeout(600.0)  # 10 минут на загрузку
                    )
                    return pull_response.status_code == 200
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при проверке модели: {e}")
            return False
    
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Отправить запрос в Ollama."""
        client = await self._get_client()
        
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
            
        try:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            
            return LLMResponse(
                content=data.get("message", {}).get("content", ""),
                model=self.model,
                usage={
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                },
                finish_reason=data.get("done_reason", "stop")
            )
        except Exception as e:
            logger.error(f"Ошибка Ollama chat: {e}")
            raise
    
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Стриминг ответа от Ollama."""
        client = await self._get_client()
        
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
            
        try:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
        except Exception as e:
            logger.error(f"Ошибка Ollama stream: {e}")
            raise


class OpenRouterClient(LLMClient):
    """
    Клиент для облачной LLM через OpenRouter.
    
    Используется для:
    - Суммаризации статей
    - Сравнения статей
    - Объяснения сложных концепций
    """
    
    DEFAULT_MODEL = "tngtech/deepseek-r1t2-chimera:free"  # Бесплатная модель с хорошим качеством
    BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        timeout: float = 120.0
    ):
        config = load_config()
        self.api_key = api_key or config.LLM_API_KEY
        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout
        self._client: Optional[AsyncOpenAI] = None
        
    async def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.BASE_URL,
                api_key=self.api_key,
                timeout=self.timeout,
                max_retries=3,
            )
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None
    
    async def is_available(self) -> bool:
        """Проверить доступность OpenRouter."""
        if not self.api_key:
            logger.warning("OpenRouter API key не настроен")
            return False
        try:
            client = await self._get_client()
            # Простой тест - попробуем получить список моделей
            models = await client.models.list()
            return True
        except Exception as e:
            logger.warning(f"OpenRouter недоступен: {e}")
            return False
    
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Отправить запрос в OpenRouter."""
        client = await self._get_client()
        
        try:
            completion = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens or 4096,
            )
            
            return LLMResponse(
                content=completion.choices[0].message.content or "",
                model=self.model,
                usage={
                    "prompt_tokens": completion.usage.prompt_tokens if completion.usage else 0,
                    "completion_tokens": completion.usage.completion_tokens if completion.usage else 0,
                } if completion.usage else None,
                finish_reason=completion.choices[0].finish_reason
            )
        except Exception as e:
            logger.error(f"Ошибка OpenRouter chat: {e}")
            raise
    
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Стриминг ответа от OpenRouter."""
        client = await self._get_client()
        
        try:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens or 4096,
                stream=True,
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Ошибка OpenRouter stream: {e}")
            raise
