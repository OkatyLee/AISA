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

# Настройка логирования
logger = setup_logger(name="api_logger", log_file="logs/api.log", level=logging.INFO)

app = FastAPI(title="Scientific Assistant API", version="0.4.0")

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
class UserLibrary(BaseModel):
    papers: List[Dict[str, Any]]
    total_count: int
    user_id: int

class TelegramInitData(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

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
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Получение библиотеки пользователя с пагинацией
    
    Args:
        page: Номер страницы (начиная с 1)
        per_page: Количество элементов на странице
        current_user: Данные текущего пользователя
        
    Returns:
        UserLibrary: Библиотека пользователя
    """
    try:
        user_id = current_user["user_id"]
        logger.info(f"Запрос библиотеки для пользователя {user_id}, страница {page}")
        
        # Получаем общее количество статей
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
                "categories": paper.get("categories", []),
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
    paper_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Удаление статьи из библиотеки"""
    try:
        user_id = current_user["user_id"]
        success = await db.delete_paper(user_id, paper_id)
        
        if success:
            logger.info(f"Пользователь {user_id} удалил статью {paper_id}")
            return {"message": "Статья удалена", "success": True}
        else:
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
