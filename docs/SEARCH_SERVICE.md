# SearchService - Документация

## Обзор

`SearchService` - это центральный сервис для поиска научных статей через различные API источники. Он предоставляет унифицированный интерфейс для работы с множественными поисковыми сервисами, поддерживает параллельный поиск, агрегацию результатов и обработку ошибок.

## Возможности

- **Мультисервисный поиск**: Поддержка ArXiv, IEEE Xplore, NCBI PubMed и возможность добавления новых сервисов
- **Параллельное выполнение**: Одновременный поиск через несколько сервисов для ускорения работы
- **Агрегация результатов**: Объединение, дедупликация и сортировка результатов
- **Обработка ошибок**: Graceful handling ошибок отдельных сервисов
- **Расширяемость**: Легкое добавление новых поисковых сервисов
- **Автоопределение сервиса**: Автоматическое определение подходящего сервиса по URL статьи

## Архитектура

### Классы

#### `SearchResult`
Результат поиска от одного сервиса.

```python
class SearchResult:
    def __init__(self, source: str, papers: List[Paper], error: Optional[str] = None):
        self.source = source      # Название сервиса
        self.papers = papers      # Список найденных статей
        self.error = error        # Ошибка (если есть)
        self.success = error is None  # Флаг успешности
```

#### `SearchService`
Основной класс для управления поисковыми сервисами.

### Поддерживаемые сервисы по умолчанию

1. **ArXiv** (`arxiv`) - arXiv.org препринты
2. **IEEE** (`ieee`) - IEEE Xplore Digital Library
3. **NCBI** (`ncbi`) - PubMed/NCBI базы данных

## API Reference

### Инициализация

```python
# Использование всех доступных сервисов по умолчанию
search_service = SearchService()

# Использование пользовательского набора сервисов
custom_services = {
    'arxiv': ArxivSearcher(),
    'ieee': IEEESearcher()
}
search_service = SearchService(services=custom_services)
```

### Основные методы

#### `search_papers(query, limit=10, services=None, concurrent=True)`

Поиск статей через выбранные сервисы.

**Параметры:**
- `query` (str): Поисковый запрос
- `limit` (int): Максимальное количество результатов на сервис (по умолчанию 10)
- `services` (List[str], optional): Список сервисов для использования. Если None, используются все
- `concurrent` (bool): Выполнять поиск параллельно (по умолчанию True)

**Возвращает:**
- `Dict[str, SearchResult]`: Словарь с результатами поиска по каждому сервису

**Пример:**
```python
results = await search_service.search_papers(
    query="machine learning",
    limit=5,
    services=['arxiv', 'ieee'],
    concurrent=True
)
```

#### `get_paper_by_url(url)`

Получение статьи по URL с автоопределением сервиса.

**Параметры:**
- `url` (str): URL статьи

**Возвращает:**
- `Optional[Paper]`: Объект Paper или None, если статья не найдена

**Пример:**
```python
paper = await search_service.get_paper_by_url("https://arxiv.org/abs/2301.00001")
```

#### `aggregate_results(search_results, remove_duplicates=True, sort_by='relevance')`

Агрегация результатов поиска от всех сервисов.

**Параметры:**
- `search_results` (Dict[str, SearchResult]): Результаты поиска
- `remove_duplicates` (bool): Удалять дубликаты статей (по умолчанию True)
- `sort_by` (str): Критерий сортировки ('relevance', 'date', 'title')

**Возвращает:**
- `List[Paper]`: Объединенный и отсортированный список статей

#### `get_search_statistics(search_results)`

Получение статистики поиска.

**Параметры:**
- `search_results` (Dict[str, SearchResult]): Результаты поиска

**Возвращает:**
- `Dict[str, Any]`: Словарь со статистикой

### Управление сервисами

#### `add_service(name, service)`

Добавление нового поискового сервиса.

**Параметры:**
- `name` (str): Название сервиса
- `service` (PaperSearcher): Экземпляр класса, наследующего PaperSearcher

#### `remove_service(name)`

Удаление поискового сервиса.

#### `get_available_services()`

Получение списка доступных сервисов.

## Примеры использования

### Базовый поиск

```python
import asyncio
from services.search_service import SearchService

async def basic_search():
    search_service = SearchService()
    
    # Поиск статей
    results = await search_service.search_papers("neural networks", limit=5)
    
    # Обработка результатов
    for service_name, result in results.items():
        if result.success:
            print(f"{service_name}: найдено {len(result.papers)} статей")
            for paper in result.papers:
                print(f"  - {paper.title}")
        else:
            print(f"{service_name}: ошибка - {result.error}")

asyncio.run(basic_search())
```

### Агрегация результатов

```python
async def aggregated_search():
    search_service = SearchService()
    
    # Поиск
    results = await search_service.search_papers("artificial intelligence")
    
    # Агрегация с удалением дубликатов
    all_papers = search_service.aggregate_results(
        results, 
        remove_duplicates=True, 
        sort_by='date'
    )
    
    print(f"Найдено {len(all_papers)} уникальных статей")
    
    # Статистика
    stats = search_service.get_search_statistics(results)
    print(f"Успешных сервисов: {stats['successful_services']}")
    print(f"Общее количество статей: {stats['total_papers']}")
```

### Добавление пользовательского сервиса

```python
from services.paper import PaperSearcher

class CustomSearcher(PaperSearcher):
    async def search_papers(self, query: str, limit: int = 10):
        # Ваша реализация поиска
        pass
    
    async def get_paper_by_url(self, url: str):
        # Ваша реализация получения по URL
        pass

# Использование
search_service = SearchService()
search_service.add_service('custom', CustomSearcher())
```

## Обработка ошибок

SearchService gracefully обрабатывает ошибки отдельных сервисов:

```python
results = await search_service.search_papers("test query")

for service_name, result in results.items():
    if result.success:
        # Обработка успешных результатов
        process_papers(result.papers)
    else:
        # Логирование ошибки, но продолжение работы
        logger.warning(f"Service {service_name} failed: {result.error}")
```

## Производительность

### Параллельный vs Последовательный поиск

```python
# Параллельный поиск (быстрее)
results = await search_service.search_papers(
    "query", 
    concurrent=True  # По умолчанию
)

# Последовательный поиск (медленнее, но меньше нагрузка на API)
results = await search_service.search_papers(
    "query", 
    concurrent=False
)
```

### Оптимизация

- Используйте параллельный поиск для скорости
- Ограничивайте количество результатов для экономии API квот
- Кэшируйте результаты для повторяющихся запросов

## Логирование

SearchService использует стандартную систему логирования:

```python
# Логи сохраняются в logs/search_service.log
# Уровни: INFO, WARNING, ERROR
```

## Расширение функциональности

### Создание нового поискового сервиса

1. Наследуйте от `PaperSearcher`
2. Реализуйте абстрактные методы
3. Добавьте в SearchService

```python
class MySearcher(PaperSearcher):
    async def __aenter__(self):
        # Инициализация подключения
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Закрытие подключения
        pass
    
    async def search_papers(self, query: str, limit: int = 10) -> List[Paper]:
        # Реализация поиска
        pass
    
    async def get_paper_by_url(self, url: str) -> Paper:
        # Реализация получения по URL
        pass
```

## Требования

- Python 3.8+
- httpx для HTTP запросов
- Настроенные API ключи для соответствующих сервисов

## Конфигурация

Убедитесь, что в конфигурации установлены необходимые API ключи:

```python
# config/config.py
IEEE_API_KEY = "your_ieee_key"
NCBI_API_KEY = "your_ncbi_key"
# ArXiv не требует ключа
```
