from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
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

# Импорты для новой функциональности
from services.search import SearchService
from services.search.arxiv_service import ArxivSearcher
from services.search.semantic_scholar_service import SemanticScholarSearcher
from services.search.ieee_service import IEEESearcher
from services.search.ncbi_service import NCBISearcher
from services.utils.paper import Paper
from nlp.intent_classifier import RuleBasedIntentClassifier
from nlp.entity_classifier import RuleBasedEntityExtractor
from services.utils.search_utils import SearchUtils
import asyncio

# Настройка логирования
logger = setup_logger(name="api_logger", log_file="logs/api.log", level=logging.DEBUG)

app = FastAPI(title="Scientific Assistant API", version="1.0.0")

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

@app.post("/api/v1/chat")
async def chat_with_assistant(
    chat_request: ChatRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Чат с AI ассистентом для обработки естественного языка
    
    TODO: не работает извлечение намерений. Переписать логику общения.
    """
    try:
        user_id = current_user["user_id"]
        logger.info(f"Пользователь {user_id} отправил сообщение: '{chat_request.message}'")
        
        response = {
            "intent": None,
            "confidence": None,
            "entities": None,
            "response_text": "Извините, функция временно недоступна.",
            "action": None,
            "data": {}
        }
        
        return ''
        
        # Инициализируем классификатор намерений
        intent_classifier = RuleBasedIntentClassifier()
        entity_extractor = RuleBasedEntityExtractor()
        
        # Определяем намерение
        intent_result = intent_classifier.classify(chat_request.message)
        entities = await entity_extractor.extract(chat_request.message, None)

        response = {
            "intent": intent_result.intent.value,
            "confidence": intent_result.confidence,
            "entities": entities,
            "response_text": "",
            "action": None,
            "data": {}
        }
        
        # Обрабатываем намерения
        if intent_result.intent.value == "search":
            query = entities.get("query", chat_request.message)
            response["action"] = "search"
            response["data"] = {
                "query": query,
                "filters": {
                    "author": entities.get("author"),
                    "year": entities.get("year"),
                    "journal": entities.get("journal")
                }
            }
            response["response_text"] = f"Ищу статьи по запросу: {query}"
            
        elif intent_result.intent.value == "list_saved":
            response["action"] = "show_library"
            response["response_text"] = "Показываю вашу библиотеку статей"
            
        elif intent_result.intent.value == "get_summary":
            urls = entities.get("urls", [])
            if urls:
                response["action"] = "summarize"
                response["data"] = {"urls": urls}
                response["response_text"] = f"Готовлю краткое изложение статьи: {urls[0]}"
            else:
                response["response_text"] = "Пожалуйста, предоставьте ссылку на статью для создания резюме"
                
        elif intent_result.intent.value == "help":
            response["response_text"] = (
                "Я могу помочь вам:\n"
                "🔍 Искать научные статьи\n"
                "📚 Управлять библиотекой\n"
                "🎯 Получать рекомендации\n"
                "📄 Создавать резюме статей\n\n"
                "Просто напишите, что вас интересует!"
            )
            
        elif intent_result.intent.value == "greeting":
            response["response_text"] = (
                "Привет! Я ваш научный ассистент. "
                "Я помогу найти и организовать научные статьи. "
                "Что вас интересует?"
            )
            
        else:
            response["response_text"] = (
                "Я не совсем понял ваш запрос. "
                "Попробуйте спросить о поиске статей, библиотеке или помощи."
            )
        
        return response
        
    except Exception as e:
        logger.error(f"Ошибка обработки чата: {e}")
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
