"""
Система метрик для мониторинга работы бота
"""

import time
from collections import defaultdict, deque
from typing import Dict, Any
from datetime import datetime, timedelta
from utils import setup_logger

logger = setup_logger(name="metrics", level="INFO")

class MetricsCollector:
    """Сбор и анализ метрик работы бота"""
    
    def __init__(self, max_history_size: int = 1000):
        self.max_history_size = max_history_size
        
        # Счетчики
        self.counters = defaultdict(int)
        
        # История операций
        self.operation_history = deque(maxlen=max_history_size)
        
        # Время выполнения операций
        self.timing_data = defaultdict(list)
        
        # Ошибки
        self.error_counts = defaultdict(int)
        
        # Пользовательская активность
        self.user_activity = defaultdict(lambda: defaultdict(int))
        
    def record_operation(self, operation: str, user_id: int, duration: float = None, success: bool = True):
        """Запись операции"""
        timestamp = datetime.now()
        
        # Увеличиваем счетчик
        self.counters[operation] += 1
        
        # Записываем в историю
        record = {
            'operation': operation,
            'user_id': user_id,
            'timestamp': timestamp,
            'duration': duration,
            'success': success
        }
        self.operation_history.append(record)
        
        # Время выполнения
        if duration is not None:
            self.timing_data[operation].append(duration)
            # Ограничиваем размер истории времени
            if len(self.timing_data[operation]) > 100:
                self.timing_data[operation] = self.timing_data[operation][-100:]
        
        # Пользовательская активность
        self.user_activity[user_id][operation] += 1
        
        # Логируем
        if success:
            logger.info(f"Operation {operation} completed by user {user_id}" + 
                       (f" in {duration:.2f}s" if duration else ""))
        else:
            self.error_counts[operation] += 1
            logger.warning(f"Operation {operation} failed for user {user_id}")
    
    def get_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Получение статистики за указанное количество часов"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Фильтруем записи за указанный период
        recent_operations = [
            record for record in self.operation_history 
            if record['timestamp'] >= cutoff_time
        ]
        
        # Подсчитываем статистику
        operation_counts = defaultdict(int)
        successful_operations = defaultdict(int)
        failed_operations = defaultdict(int)
        
        for record in recent_operations:
            operation = record['operation']
            operation_counts[operation] += 1
            
            if record['success']:
                successful_operations[operation] += 1
            else:
                failed_operations[operation] += 1
        
        # Средние времена выполнения
        avg_timings = {}
        for operation, times in self.timing_data.items():
            if times:
                avg_timings[operation] = sum(times) / len(times)
        
        # Активные пользователи
        active_users = len(set(record['user_id'] for record in recent_operations))
        
        return {
            'period_hours': hours,
            'total_operations': len(recent_operations),
            'active_users': active_users,
            'operation_counts': dict(operation_counts),
            'successful_operations': dict(successful_operations),
            'failed_operations': dict(failed_operations),
            'average_timings': avg_timings,
            'error_rates': {
                op: failed_operations[op] / operation_counts[op] * 100
                for op in operation_counts
                if operation_counts[op] > 0
            }
        }
    
    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Статистика по конкретному пользователю"""
        user_operations = [
            record for record in self.operation_history 
            if record['user_id'] == user_id
        ]
        
        if not user_operations:
            return {'message': 'No activity found for this user'}
        
        # Первая и последняя активность
        first_activity = min(user_operations, key=lambda x: x['timestamp'])['timestamp']
        last_activity = max(user_operations, key=lambda x: x['timestamp'])['timestamp']
        
        # Подсчет операций
        operation_counts = defaultdict(int)
        for record in user_operations:
            operation_counts[record['operation']] += 1
        
        return {
            'user_id': user_id,
            'total_operations': len(user_operations),
            'first_activity': first_activity.isoformat(),
            'last_activity': last_activity.isoformat(),
            'operation_breakdown': dict(operation_counts)
        }
    
    def log_daily_stats(self):
        """Логирование ежедневной статистики"""
        stats = self.get_stats(24)
        logger.info(f"Daily stats: {stats}")

# Глобальный экземпляр метрик
metrics = MetricsCollector()

def track_operation(operation: str):
    """Декоратор для отслеживания операций"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            user_id = None
            
            # Пытаемся извлечь user_id из аргументов
            for arg in args:
                if hasattr(arg, 'from_user') and hasattr(arg.from_user, 'id'):
                    user_id = arg.from_user.id
                    break
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                metrics.record_operation(operation, user_id or 0, duration, True)
                return result
            except Exception as e:
                duration = time.time() - start_time
                metrics.record_operation(operation, user_id or 0, duration, False)
                raise
        
        return wrapper
    return decorator
