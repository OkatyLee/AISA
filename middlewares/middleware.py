from aiogram import Dispatcher
from aiogram.types import Message, TelegramObject
from typing import Callable, Awaitable, Dict, Any, Set
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from collections import defaultdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class Middleware(BaseMiddleware):
    def __init__(self, config):
        self.config = config
        self.user_requests: Dict[int, list] = defaultdict(list)
        self.blocked_users: Set[int] = set()

    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]) -> Awaitable:
        
        user_id = self._get_user_id(event)
        
        if not user_id:
            return await handler(event, data)
        
        if user_id in self.blocked_users:
            logger.warning(f"Пользователь {user_id} заблокирован. Игнорирование запроса.")
            return
        
        if not await self._check_rate_limit(user_id):
            logger.warning(f"Пользователь {user_id} превысил лимит запросов. Отправка сообщения.")
            await self._send_rate_limit_message(event)
            return
        self._log_request(event, user_id)
        
        try:
            await handler(event, data)
        except Exception as e:
            logger.error(f"Error in middleware: {e}")
            raise e
        
        
    def _get_user_id(self, event: TelegramObject) -> int | None:
        if hasattr(event, 'from_user') and event.from_user:
            return event.from_user.id
        return None    
        
    def _send_error_message(self, event: TelegramObject):
        if isinstance(event, Message):
            return event.answer("❌ Произошла ошибка. Попробуйте позже.")
        
    def _log_request(self, event: TelegramObject, user_id: int):
        if isinstance(event, Message):
            logger.info(f"User {user_id} sent a message: {event.text}")
        else:
            logger.info(f"User {user_id} triggered an event: {event.__class__.__name__}")
            
    async def _check_rate_limit(self, user_id: int) -> bool:
        
        
        now = datetime.now()
        
        user_requests = self.user_requests[user_id]
        user_requests[:] = [req_time for req_time in user_requests 
                           if now - req_time < timedelta(hours=1)]
        
        if len(user_requests) >= self.config.MAX_REQUESTS_PER_HOUR:
            return False
        
        minute_requests = [req_time for req_time in user_requests 
                           if now - req_time < timedelta(minutes=1)]
        
        if len(minute_requests) >= self.config.MAX_REQUESTS_PER_MINUTE:
            return False
            
        user_requests.append(now)
        return True
        
    async def _send_rate_limit_message(self, event: TelegramObject):
        """Send a message to the user indicating they have exceeded the rate limit."""
        if isinstance(event, Message):
            await event.answer("⚠️ Превышен лимит запросов. Попробуйте позже.")
