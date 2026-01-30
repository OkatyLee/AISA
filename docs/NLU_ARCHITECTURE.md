# NLU & Chat System Architecture

## Обзор

Новая система NLU (Natural Language Understanding) и чата обеспечивает гибкое понимание пользовательских запросов через LLM.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                      Telegram Bot                            │
│                     (handlers/chat_handler.py)               │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      NLU Pipeline                            │
│                     (nlu/pipeline.py)                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ Intent Classifier│  │ Entity Extractor│  │Context Mgr  │  │
│  │  (LLM-based)    │  │   (LLM-based)   │  │ (SQLite)    │  │
│  └────────┬────────┘  └────────┬────────┘  └──────┬──────┘  │
└───────────┼────────────────────┼─────────────────┼──────────┘
            │                    │                  │
            ▼                    ▼                  │
┌─────────────────────────────────────────────────────────────┐
│                     LLM Services                             │
│                   (services/llm/)                            │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │    OllamaClient     │  │     OpenRouterClient         │  │
│  │  (локальная LLM)    │  │    (облачная LLM)            │  │
│  │  - Intent classify  │  │    - Суммаризация            │  │
│  │  - Entity extract   │  │    - Сравнение статей        │  │
│  │  - Обычный чат      │  │    - Объяснение концепций    │  │
│  └─────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Компоненты

### 1. NLU Module (`nlu/`)

#### Models (`nlu/models/`)
- **intents.py** - Enum Intent и IntentResult
- **entities.py** - EntityType, Entity, EntityExtractionResult  
- **context.py** - UserContext, ConversationTurn

#### Classifiers (`nlu/classifiers/`)
- **LLMIntentClassifier** - Классификация намерений через локальную LLM
- **LLMEntityExtractor** - Извлечение сущностей через локальную LLM

#### Pipeline (`nlu/pipeline.py`)
- **NLUPipeline** - Главный пайплайн обработки сообщений

#### Context Manager (`nlu/context_manager.py`)
- **ContextManager** - Управление контекстом диалога (SQLite + кэш)

### 2. LLM Services (`services/llm/`)

#### Clients (`services/llm/client.py`)
- **OllamaClient** - Клиент для локальной LLM (Ollama)
- **OpenRouterClient** - Клиент для облачной LLM (OpenRouter)

#### Services
- **ChatService** - Сервис для обычного чата
- **PaperService** - Сервис для работы со статьями (суммаризация, сравнение)

## Сценарии использования

### 1. Обычный чат
```
User: "Привет, как дела?"
         │
         ▼
    NLU Pipeline
         │
    Intent: GREETING
         │
         ▼
    OllamaClient (локально)
         │
         ▼
    "Привет! Я научный ассистент..."
```

### 2. Поиск статей
```
User: "Найди статьи про machine learning за 2024 год"
         │
         ▼
    NLU Pipeline
         │
    Intent: SEARCH
    Entities: topic="machine learning", year=2024
         │
         ▼
    SearchService → ArXiv/PubMed/IEEE
         │
         ▼
    Результаты поиска
```

### 3. Суммаризация статьи
```
User: "Сделай резюме первой статьи"
         │
         ▼
    NLU Pipeline
         │
    Intent: GET_SUMMARY
    Entities: article_ref="первая"
         │
         ▼
    Context: получаем статью из контекста
         │
         ▼
    OpenRouterClient (облачная LLM)
         │
         ▼
    PDF с анализом статьи
```

## Намерения (Intents)

| Intent | Описание | LLM |
|--------|----------|-----|
| SEARCH | Поиск статей | Локальная |
| LIST_LIBRARY | Показать библиотеку | - |
| SAVE_ARTICLE | Сохранить статью | - |
| GET_SUMMARY | Суммаризация | Облачная |
| EXPLAIN | Объяснение | Облачная |
| COMPARE | Сравнение | Облачная |
| HELP | Помощь | Локальная |
| GREETING | Приветствие | Локальная |
| CHAT | Обычный разговор | Локальная |

## Конфигурация

### Docker Compose
```yaml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
```

### Константы (`config/constants.py`)
```python
OLLAMA_BASE_URL = "http://ollama:11434"
OLLAMA_MODEL = "qwen2.5:3b"
OPENROUTER_CHAT_MODEL = "qwen/qwen3-30b-a3b:free"
```

## Миграция со старого кода

### Старый код (deprecated):
```python
from nlp import RuleBasedIntentClassifier
from utils.nlu.intents import Intent
```

### Новый код:
```python
from nlu import NLUPipeline, Intent
from nlu.classifiers import LLMIntentClassifier
```

## Fallback

Если Ollama недоступна:
1. Intent Classifier переключается на rule-based fallback
2. Entity Extractor использует regex-паттерны
3. Chat переключается на OpenRouter (если доступен)

## Тестирование

```bash
# Запуск Docker с Ollama
docker-compose up -d ollama

# Проверка доступности
curl http://localhost:11434/api/tags

# Загрузка модели
curl -X POST http://localhost:11434/api/pull -d '{"name": "qwen2.5:3b"}'
```
