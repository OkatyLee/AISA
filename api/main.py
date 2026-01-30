from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import hmac
import json
import urllib.parse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from database import SQLDatabase as db
from config.config import load_config
import logging
from utils import setup_logger
import time

# Импорты для новой функциональности
from services.search import SearchService
from services.search.arxiv_service import ArxivSearcher
from services.search.semantic_scholar_service import SemanticScholarSearcher
from services.search.ieee_service import IEEESearcher
from services.search.ncbi_service import NCBISearcher
from services.utils.paper import Paper
from nlu import NLUPipeline, Intent  # Новый NLU
from nlu.classifiers import LLMIntentClassifier, LLMEntityExtractor
from services.utils.search_utils import SearchUtils
from services.llm import ChatService, PaperService
import asyncio

# Настройка логирования
logger = setup_logger(name="api_logger", log_file="logs/api.log", level=logging.DEBUG)

app = FastAPI(title="Scientific Assistant API", version="1.0.0")
start_time = time.time()

# Глобальные сервисы (инициализируются при старте)
_nlu_pipeline: NLUPipeline = None
_chat_service: ChatService = None
_paper_service: PaperService = None
# Конфигурация
config = load_config()

# CORS настройки для Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://t.me", "https://web.telegram.org"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Статические файлы и шаблоны
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")
templates = Jinja2Templates(directory="webapp/templates")

# Модели данных
class PaperTags(BaseModel):
    new_tags: str

class UserLibrary(BaseModel):
    papers: List[Dict[str, Any]]
    total_count: int
    user_id: int

class TelegramInitData(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = {}
    limit: int = 10
    source: Optional[str] = None  # arxiv, ieee, ncbi, semantic_scholar

class RecommendationRequest(BaseModel):
    paper_ids: List[str]
    limit: int = 10

class ChatRequest(BaseModel):
    message: str
    context: Optional[List[Dict[str, Any]]] = []


class ChatResponse(BaseModel):
    """Ответ от чат-ассистента"""
    intent: str
    confidence: float
    entities: List[Dict[str, Any]]
    response_text: str
    action: Optional[str] = None
    data: Dict[str, Any] = {}
    needs_cloud_llm: bool = False


@app.on_event("startup")
async def startup_event():
    """Инициализация сервисов при старте API."""
    global _nlu_pipeline, _chat_service, _paper_service
    
    from config.constants import OLLAMA_BASE_URL
    
    _nlu_pipeline = NLUPipeline(
        ollama_url=OLLAMA_BASE_URL,
        db_path="db/scientific_assistant.db"
    )
    _chat_service = ChatService(ollama_url=OLLAMA_BASE_URL)
    _paper_service = PaperService()
    
    await _chat_service.initialize()
    logger.info("API chat services initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Закрытие сервисов при остановке API."""
    global _nlu_pipeline, _chat_service, _paper_service
    
    if _nlu_pipeline:
        await _nlu_pipeline.close()
    if _chat_service:
        await _chat_service.close()
    if _paper_service:
        await _paper_service.close()
    
    logger.info("API chat services closed")

def validate_telegram_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """
    Валидация данных initData от Telegram
    
    Args:
        init_data: Строка с данными от Telegram
        
    Returns:
        Словарь с данными пользователя или None при ошибке
    """
    try:
        # Парсим query string
        parsed_data = urllib.parse.parse_qs(init_data)
        
        # Извлекаем hash для проверки
        received_hash = parsed_data.get('hash', [None])[0]
        if not received_hash:
            logger.warning("Нет hash в initData")
            return None
        
        # Создаем строку для проверки подписи
        auth_data = []
        for key in sorted(parsed_data.keys()):
            if key != 'hash':
                auth_data.append(f"{key}={parsed_data[key][0]}")
        
        auth_string = '\n'.join(auth_data)
        
        # Проверяем подпись
        secret_key = hmac.new(
            "WebAppData".encode(), 
            config.BOT_TOKEN.encode(), 
            hashlib.sha256
        ).digest()
        
        calculated_hash = hmac.new(
            secret_key,
            auth_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(received_hash, calculated_hash):
            logger.warning("Неверная подпись initData")
            return None
        
        # Извлекаем данные пользователя
        user_data = parsed_data.get('user', [None])[0]
        if user_data:
            user_info = json.loads(user_data)
            return {
                'user_id': user_info.get('id'),
                'username': user_info.get('username'),
                'first_name': user_info.get('first_name'),
                'last_name': user_info.get('last_name')
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка валидации initData: {e}")
        return None

def get_current_user(request: Request) -> Dict[str, Any]:
    """Получение текущего пользователя из initData"""
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data:
        init_data = request.query_params.get('initData')
    
    if not init_data:
        raise HTTPException(status_code=401, detail="Не найдены данные авторизации")
    
    user_data = validate_telegram_init_data(init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Неверные данные авторизации")
    
    return user_data

@app.get("/", response_class=HTMLResponse)
async def mini_app_root(request: Request):
    """Главная страница Mini App"""
    return templates.TemplateResponse("library.html", {"request": request})

start_time = time.time()


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint для Docker healthcheck
    Возвращает статус сервиса и время работы
    """
    uptime = time.time() - start_time
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "uptime_seconds": round(uptime, 2),
            "service": "api"
        }
    )

@app.get("/api/v1/user/info")
async def get_user_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Получение информации о текущем пользователе"""
    return {
        "user_id": current_user["user_id"],
        "username": current_user.get("username"),
        "first_name": current_user.get("first_name"),
        "last_name": current_user.get("last_name")
    }

@app.get("/api/v1/library", response_model=UserLibrary)
async def get_user_library(
    page: int = 1,
    per_page: int = 10,
    search: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Получение библиотеки пользователя с пагинацией и поиском
    
    Args:
        page: Номер страницы (начиная с 1)
        per_page: Количество элементов на странице
        search: Поисковый запрос
        current_user: Данные текущего пользователя
        
    Returns:
        UserLibrary: Библиотека пользователя
    """
    try:
        user_id = current_user["user_id"]
        logger.info(f"Запрос библиотеки для пользователя {user_id}, страница {page}, поиск: '{search}'")
        
        if search:
            all_papers = await db.search_in_library(user_id, search)
        else:
            all_papers = await db.get_user_library(user_id)
        
        total_count = len(all_papers)
        
        # Пагинация
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        papers = all_papers[start_index:end_index]
        
        # Форматируем данные для фронтенда
        formatted_papers = []
        for paper in papers:
            formatted_papers.append({
                "id": paper.get("id"),
                "title": paper.get("title", "Без названия"),
                "authors": paper.get("authors", "Неизвестные авторы"),
                "abstract": paper.get("abstract", "Аннотация не найдена"),
                "url": paper.get("url", ""),
                "publication_date": paper.get("publication_date", ""),
                "saved_at": paper.get("saved_at", ""),
                "tags": paper.get("tags", []),
                "external_id": paper.get("external_id", ""),
                "source": paper.get("source", "Неизвестный источник"),
                
            })
        
        return UserLibrary(
            papers=formatted_papers,
            total_count=total_count,
            user_id=user_id
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения библиотеки: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения библиотеки")

@app.delete("/api/v1/library/{paper_id}")
async def delete_paper_from_library(
    paper_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Удаление статьи из библиотеки"""
    try:
        user_id = current_user["user_id"]
        logger.info(f"Пользователь {user_id} пытается удалить статью {paper_id}")
        
        success = await db.delete_paper(user_id, paper_id)
        
        if success:
            logger.info(f"Пользователь {user_id} успешно удалил статью {paper_id}")
            return {"message": "Статья удалена", "success": True}
        else:
            logger.warning(f"Не удалось найти статью {paper_id} для пользователя {user_id}")
            raise HTTPException(status_code=404, detail="Статья не найдена")
            
    except Exception as e:
        logger.error(f"Ошибка удаления статьи: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления статьи")

@app.get("/api/v1/stats")
async def get_library_stats(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Получение статистики библиотеки пользователя"""
    try:
        user_id = current_user["user_id"]
        papers = await db.get_user_library(user_id)
        
        # Подсчитываем статистику по категориям
        categories_count = {}
        for paper in papers:
            if paper.get("categories"):
                for category in paper["categories"]:
                    category = category.strip()
                    categories_count[category] = categories_count.get(category, 0) + 1
        
        return {
            "total_papers": len(papers),
            "categories_distribution": categories_count,
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения статистики")

@app.post("/api/v1/library/{paper_id}/tags")
async def edit_paper_tags(
    paper_id: str,
    tags_data: PaperTags,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Изменение тегов статьи в библиотеке"""
    try:
        user_id = current_user["user_id"]
        logger.info(f"Пользователь {user_id} пытается изменить теги статьи {paper_id} на '{tags_data.new_tags}'")
        paper_id = paper_id.replace('BACKSLASH', '/')
        
        success = await db.edit_paper_tags(user_id, paper_id, tags_data.new_tags)
        
        if success:
            logger.info(f"Пользователь {user_id} успешно изменил теги статьи {paper_id}")
            return {"message": "Теги статьи изменены", "success": True}
        else:
            logger.warning(f"Не удалось найти статью {paper_id} для пользователя {user_id}")
            raise HTTPException(status_code=404, detail="Статья не найдена")
            
    except Exception as e:
        logger.error(f"Ошибка изменения тегов статьи: {e}")
        raise HTTPException(status_code=500, detail="Ошибка изменения тегов статьи")

# Новые эндпоинты для расширенной функциональности

@app.post("/api/v1/search")
async def search_papers(
    search_request: SearchRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Поиск научных статей через различные источники
    """
    try:
        user_id = current_user["user_id"]
        logger.info(f"Пользователь {user_id} ищет: '{search_request.query}'")
        
        results = []
        
        if search_request.source == "arxiv":
            async with ArxivSearcher() as searcher:
                papers = await searcher.search_papers(
                    search_request.query, 
                    limit=search_request.limit,
                    filters=search_request.filters
                )
                results = papers
        elif search_request.source == "ieee":
            async with IEEESearcher() as searcher:
                papers = await searcher.search_papers(
                    search_request.query,
                    limit=search_request.limit,
                    filters=search_request.filters
                )
                results = papers
        elif search_request.source == "ncbi":
            async with NCBISearcher() as searcher:
                papers = await searcher.search_papers(
                    search_request.query,
                    limit=search_request.limit,
                    filters=search_request.filters
                )
                results = papers
        elif search_request.source == "semantic_scholar":
            async with SemanticScholarSearcher() as searcher:
                papers = await searcher.search_papers(
                    search_request.query,
                    limit=search_request.limit,
                    filters=search_request.filters
                )
                results = papers
        else:
            # Универсальный поиск по всем источникам
            async with SearchService() as search_service:
                search_results = await search_service.search_papers(
                    search_request.query,
                    limit=search_request.limit,
                    filters=search_request.filters
                )
                results = search_service.aggregate_results(search_results, search_request.query)
        
        # Проверяем, какие статьи уже сохранены
        saved_urls = await SearchUtils._get_user_saved_urls(user_id)
        
        # Форматируем результаты для фронтенда
        formatted_results = []
        for paper in results:
            paper_dict = paper.to_dict() if hasattr(paper, 'to_dict') else paper.__dict__
            paper_dict['is_saved'] = paper_dict.get('url', '') in saved_urls
            formatted_results.append(paper_dict)
        
        return {
            "papers": formatted_results,
            "total_count": len(formatted_results),
            "query": search_request.query,
            "source": search_request.source or "all"
        }
        
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        raise HTTPException(status_code=500, detail="Ошибка выполнения поиска")

@app.post("/api/v1/recommendations")
async def get_recommendations(
    recommendation_request: RecommendationRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Получение рекомендаций на основе статей из библиотеки
    """
    try:
        user_id = current_user["user_id"]
        logger.info(f"Пользователь {user_id} запрашивает рекомендации")
        
        if recommendation_request.paper_ids:
            # Рекомендации на основе переданных ID
            papers = [Paper(external_id=paper_id) for paper_id in recommendation_request.paper_ids]
            async with SemanticScholarSearcher() as searcher:
                recommendations = await searcher.get_recommendations_for_multiple_papers(
                    papers, 
                    recommendation_request.limit
                )
        else:
            # Рекомендации на основе библиотеки пользователя
            user_papers = await db.get_user_library(user_id)
            if not user_papers:
                return {"papers": [], "total_count": 0, "message": "Библиотека пуста"}
            
            papers = [Paper(**paper) for paper in user_papers[:10]]  # Берем последние 10 статей
            async with SemanticScholarSearcher() as searcher:
                recommendations = await searcher.get_recommendations_for_multiple_papers(
                    papers, 
                    recommendation_request.limit
                )
        
        # Проверяем, какие статьи уже сохранены
        saved_urls = await SearchUtils._get_user_saved_urls(user_id)
        
        # Форматируем результаты
        formatted_results = []
        for paper in recommendations:
            paper_dict = paper.to_dict() if hasattr(paper, 'to_dict') else paper.__dict__
            paper_dict['is_saved'] = paper_dict.get('url', '') in saved_urls
            formatted_results.append(paper_dict)
        
        return {
            "papers": formatted_results,
            "total_count": len(formatted_results)
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения рекомендаций: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения рекомендаций")

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_with_assistant(
    chat_request: ChatRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Чат с AI ассистентом для обработки естественного языка.
    
    Интегрирует NLU Pipeline для понимания запросов и выполнения действий.
    """
    global _nlu_pipeline, _chat_service, _paper_service
    
    try:
        user_id = current_user["user_id"]
        message = chat_request.message.strip()
        logger.info(f"Пользователь {user_id} отправил сообщение: '{message}'")
        
        # Обработка через NLU Pipeline
        nlu_result = await _nlu_pipeline.process(user_id=user_id, message=message)
        
        intent = nlu_result.intent.intent
        entities = [
            {
                "type": e.type.value,
                "value": e.value,
                "confidence": e.confidence,
                "normalized": e.normalized_value
            }
            for e in nlu_result.entities.entities
        ]
        
        response_text = ""
        action = None
        data = {}
        
        # Обработка по интентам
        if intent == Intent.SEARCH:
            # Поиск статей
            query = nlu_result.query_params.get("query", message)
            filters = {}
            
            if nlu_result.query_params.get("year"):
                filters["year"] = nlu_result.query_params["year"]
            if nlu_result.query_params.get("author"):
                filters["author"] = nlu_result.query_params["author"]
            
            source = nlu_result.query_params.get("source")
            
            # Выполняем поиск
            try:
                search_results = []
                if source == "arxiv":
                    async with ArxivSearcher() as searcher:
                        search_results = await searcher.search_papers(query, limit=10, filters=filters)
                elif source == "ieee":
                    async with IEEESearcher() as searcher:
                        search_results = await searcher.search_papers(query, limit=10, filters=filters)
                elif source == "ncbi":
                    async with NCBISearcher() as searcher:
                        search_results = await searcher.search_papers(query, limit=10, filters=filters)
                elif source == "semantic_scholar":
                    async with SemanticScholarSearcher() as searcher:
                        search_results = await searcher.search_papers(query, limit=10, filters=filters)
                else:
                    async with SearchService() as search_service:
                        search_results = await search_service.search_papers(query, limit=10, filters=filters)
                        search_results = search_service.aggregate_results(search_results, query)
                
                # Форматируем результаты
                formatted_results = []
                for paper in search_results:
                    paper_dict = paper.to_dict() if hasattr(paper, 'to_dict') else paper.__dict__
                    formatted_results.append(paper_dict)
                
                data["papers"] = formatted_results
                data["query"] = query
                action = "show_search_results"
                
                if formatted_results:
                    response_text = f"🔍 Найдено {len(formatted_results)} статей по запросу «{query}»"
                    # Обновляем контекст с результатами поиска
                    await _nlu_pipeline.update_context(
                        user_id=user_id,
                        message=message,
                        result=nlu_result,
                        bot_response=response_text,
                        search_results=formatted_results[:10]
                    )
                else:
                    response_text = f"😔 К сожалению, по запросу «{query}» ничего не найдено. Попробуйте уточнить запрос."
                    
            except Exception as e:
                logger.error(f"Ошибка поиска: {e}")
                response_text = "❌ Произошла ошибка при поиске. Попробуйте позже."
        
        elif intent == Intent.LIST_LIBRARY:
            # Показать библиотеку
            papers = await db.get_user_library(user_id)
            formatted_papers = [
                {
                    "id": p.get("id"),
                    "title": p.get("title", "Без названия"),
                    "authors": p.get("authors", ""),
                    "url": p.get("url", ""),
                }
                for p in papers[:20]
            ]
            data["papers"] = formatted_papers
            action = "show_library"
            response_text = f"📚 В вашей библиотеке {len(papers)} статей"
        
        elif intent == Intent.GET_SUMMARY:
            # Суммаризация статьи
            article = nlu_result.query_params.get("article")
            if article:
                try:
                    summary = await _paper_service.summarize(article)
                    data["summary"] = summary
                    data["article"] = article
                    action = "show_summary"
                    response_text = summary
                except Exception as e:
                    logger.error(f"Ошибка суммаризации: {e}")
                    response_text = "❌ Не удалось создать саммари. Попробуйте позже."
            else:
                response_text = "🤔 Укажите статью для суммаризации. Например: «Кратко о первой статье»"
        
        elif intent == Intent.EXPLAIN:
            # Объяснение концепции или статьи
            article = nlu_result.query_params.get("article")
            if article:
                try:
                    explanation = await _paper_service.explain(article)
                    data["explanation"] = explanation
                    data["article"] = article
                    action = "show_explanation"
                    response_text = explanation
                except Exception as e:
                    logger.error(f"Ошибка объяснения: {e}")
                    response_text = "❌ Не удалось создать объяснение. Попробуйте позже."
            else:
                # Общее объяснение через чат
                context = await _nlu_pipeline.context_manager.get_context(user_id)
                response_text = await _chat_service.chat(message, context=context)
                action = "chat_response"
        
        elif intent == Intent.COMPARE:
            # Сравнение статей
            articles = nlu_result.query_params.get("articles", [])
            if len(articles) >= 2:
                try:
                    comparison = await _paper_service.compare(articles[:5])
                    data["comparison"] = comparison
                    data["articles"] = articles
                    action = "show_comparison"
                    response_text = comparison
                except Exception as e:
                    logger.error(f"Ошибка сравнения: {e}")
                    response_text = "❌ Не удалось сравнить статьи. Попробуйте позже."
            else:
                response_text = "🤔 Для сравнения нужно минимум 2 статьи. Сначала выполните поиск."
        
        elif intent == Intent.SAVE_ARTICLE:
            # Сохранение статьи
            article = nlu_result.query_params.get("article")
            if article:
                success = await db.save_paper(user_id, article)
                if success:
                    response_text = f"✅ Статья «{article.get('title', 'Без названия')[:50]}...» сохранена в библиотеку"
                    action = "article_saved"
                else:
                    response_text = "❌ Не удалось сохранить статью"
            else:
                response_text = "🤔 Укажите статью для сохранения. Например: «Сохрани первую статью»"
        
        elif intent == Intent.DELETE_ARTICLE:
            # Удаление статьи
            article = nlu_result.query_params.get("article")
            if article and article.get("id"):
                success = await db.delete_paper(user_id, article["id"])
                if success:
                    response_text = "🗑️ Статья удалена из библиотеки"
                    action = "article_deleted"
                else:
                    response_text = "❌ Не удалось удалить статью"
            else:
                response_text = "🤔 Укажите статью для удаления"
        
        elif intent == Intent.HELP:
            response_text = """🤖 **Я — AI Scientific Assistant (AISA)**

Вот что я умею:

🔍 **Поиск статей:**
• «Найди статьи про machine learning»
• «Статьи по NLP за 2024 год»
• «Поиск в arxiv: transformers»

📚 **Работа с библиотекой:**
• «Покажи мою библиотеку»
• «Сохрани первую статью»

📝 **Анализ статей:**
• «Кратко о первой статье»
• «Объясни вторую статью»
• «Сравни статьи 1 и 2»

Просто напишите, что вас интересует!"""
            action = "show_help"
        
        elif intent == Intent.GREETING:
            response_text = "👋 Привет! Я AISA — ваш научный ассистент. Чем могу помочь? Напишите /help для списка команд."
            action = "greeting"
        
        else:
            # CHAT или UNKNOWN — обычный чат
            context = await _nlu_pipeline.context_manager.get_context(user_id)
            response_text = await _chat_service.chat(message, context=context)
            action = "chat_response"
        
        # Обновляем контекст (если ещё не обновили)
        if action not in ["show_search_results"]:
            await _nlu_pipeline.update_context(
                user_id=user_id,
                message=message,
                result=nlu_result,
                bot_response=response_text
            )
        
        return ChatResponse(
            intent=intent.value,
            confidence=nlu_result.intent.confidence,
            entities=entities,
            response_text=response_text,
            action=action,
            data=data,
            needs_cloud_llm=nlu_result.needs_cloud_llm
        )
        
    except Exception as e:
        logger.error(f"Ошибка обработки чата: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка обработки сообщения")

@app.post("/api/v1/library/save")
async def save_paper_to_library(
    paper: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Сохранение статьи в библиотеку"""
    try:
        user_id = current_user["user_id"]
        paper = paper.get('paper') or paper
        logger.debug(f"Пользователь {user_id} пытается сохранить статью: {paper}")
        logger.info(f"Пользователь {user_id} сохраняет статью {paper['external_id']}")

        success = await db.save_paper(user_id, paper)
        if success:
            return {"message": "Статья сохранена", "success": True}
        else:
            return {"message": "Ошибка сохранения статьи", "success": False}

    except Exception as e:
        logger.error(f"Ошибка сохранения статьи: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сохранения статьи")


@app.post("/api/v1/chat/test")
async def chat_test(chat_request: ChatRequest):
    """
    Тестовый endpoint для чата без авторизации.
    
    Использует фиктивный user_id = 0 для тестирования.
    """
    global _nlu_pipeline, _chat_service
    
    try:
        user_id = 0  # Тестовый пользователь
        message = chat_request.message.strip()
        logger.info(f"Тестовый запрос: '{message}'")
        
        # Обработка через NLU Pipeline
        nlu_result = await _nlu_pipeline.process(user_id=user_id, message=message)
        
        intent = nlu_result.intent.intent
        entities = [
            {
                "type": e.type.value,
                "value": e.value,
                "confidence": e.confidence,
                "normalized": e.normalized_value
            }
            for e in nlu_result.entities.entities
        ]
        
        # Для теста просто возвращаем NLU результат
        response_text = ""
        if intent == Intent.SEARCH:
            query = nlu_result.query_params.get("query", message)
            response_text = f"🔍 Распознан поиск: «{query}»"
        elif intent == Intent.CHAT:
            context = await _nlu_pipeline.context_manager.get_context(user_id)
            response_text = await _chat_service.chat(message, context=context)
        else:
            response_text = f"Распознан интент: {intent.value}"
        
        return ChatResponse(
            intent=intent.value,
            confidence=nlu_result.intent.confidence,
            entities=entities,
            response_text=response_text,
            action="test",
            data={"query_params": nlu_result.query_params},
            needs_cloud_llm=nlu_result.needs_cloud_llm
        )
        
    except Exception as e:
        logger.error(f"Ошибка тестового чата: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/chat/stream")
async def chat_stream(
    chat_request: ChatRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Streaming чат с AI ассистентом.
    
    Возвращает Server-Sent Events (SSE) для потокового вывода.
    """
    global _nlu_pipeline, _chat_service
    
    user_id = current_user["user_id"]
    message = chat_request.message.strip()
    
    async def generate():
        try:
            # Сначала обрабатываем через NLU
            nlu_result = await _nlu_pipeline.process(user_id=user_id, message=message)
            intent = nlu_result.intent.intent
            
            # Отправляем метаданные
            metadata = {
                "event": "metadata",
                "intent": intent.value,
                "confidence": nlu_result.intent.confidence,
                "entities": [
                    {"type": e.type.value, "value": e.value}
                    for e in nlu_result.entities.entities
                ]
            }
            yield f"data: {json.dumps(metadata, ensure_ascii=False)}\n\n"
            
            # Для поиска выполняем его и возвращаем результат
            if intent == Intent.SEARCH:
                query = nlu_result.query_params.get("query", message)
                yield f"data: {json.dumps({'event': 'text', 'content': f'🔍 Ищу статьи по запросу «{query}»...'}, ensure_ascii=False)}\n\n"
                
                try:
                    async with SearchService() as search_service:
                        search_results = await search_service.search_papers(query, limit=10)
                        search_results = search_service.aggregate_results(search_results, query)
                    
                    formatted_results = []
                    for paper in search_results:
                        paper_dict = paper.to_dict() if hasattr(paper, 'to_dict') else paper.__dict__
                        formatted_results.append(paper_dict)
                    
                    result_event = {
                        "event": "search_results",
                        "papers": formatted_results,
                        "query": query,
                        "count": len(formatted_results)
                    }
                    yield f"data: {json.dumps(result_event, ensure_ascii=False)}\n\n"
                    
                except Exception as e:
                    logger.error(f"Ошибка поиска: {e}")
                    yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            
            # Для чата стримим ответ
            elif intent in [Intent.CHAT, Intent.UNKNOWN, Intent.GREETING, Intent.HELP]:
                context = await _nlu_pipeline.context_manager.get_context(user_id)
                
                full_response = ""
                async for chunk in _chat_service.chat_stream(message, context=context):
                    full_response += chunk
                    yield f"data: {json.dumps({'event': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
                
                # Обновляем контекст
                await _nlu_pipeline.update_context(
                    user_id=user_id,
                    message=message,
                    result=nlu_result,
                    bot_response=full_response
                )
            
            else:
                # Для других интентов — обычный ответ
                yield f"data: {json.dumps({'event': 'text', 'content': f'Распознан интент: {intent.value}'}, ensure_ascii=False)}\n\n"
            
            # Завершение
            yield f"data: {json.dumps({'event': 'done'})}\n\n"
            
        except Exception as e:
            logger.error(f"Ошибка streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/v1/chat/stream/test")
async def chat_stream_test(chat_request: ChatRequest):
    """
    Тестовый streaming endpoint без авторизации.
    """
    global _nlu_pipeline, _chat_service
    
    user_id = 0
    message = chat_request.message.strip()
    
    async def generate():
        try:
            nlu_result = await _nlu_pipeline.process(user_id=user_id, message=message)
            intent = nlu_result.intent.intent
            
            # Метаданные
            metadata = {
                "event": "metadata",
                "intent": intent.value,
                "confidence": nlu_result.intent.confidence,
                "query_params": nlu_result.query_params
            }
            yield f"data: {json.dumps(metadata, ensure_ascii=False)}\n\n"
            
            if intent == Intent.SEARCH:
                query = nlu_result.query_params.get("query", message)
                yield f"data: {json.dumps({'event': 'text', 'content': f'🔍 Поиск: «{query}»'}, ensure_ascii=False)}\n\n"
                
                async with SearchService() as search_service:
                    search_results = await search_service.search_papers(query, limit=5)
                    search_results = search_service.aggregate_results(search_results, query)
                
                for paper in search_results:
                    paper_dict = paper.to_dict() if hasattr(paper, 'to_dict') else paper.__dict__
                    yield f"data: {json.dumps({'event': 'paper', 'paper': paper_dict}, ensure_ascii=False)}\n\n"
                
            elif intent in [Intent.CHAT, Intent.UNKNOWN]:
                context = await _nlu_pipeline.context_manager.get_context(user_id)
                async for chunk in _chat_service.chat_stream(message, context=context):
                    yield f"data: {json.dumps({'event': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
            
            else:
                yield f"data: {json.dumps({'event': 'text', 'content': f'Intent: {intent.value}'}, ensure_ascii=False)}\n\n"
            
            yield f"data: {json.dumps({'event': 'done'})}\n\n"
            
        except Exception as e:
            logger.error(f"Ошибка: {e}", exc_info=True)
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
