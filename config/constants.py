"""
Статичные константы приложения

Здесь должны быть только константы, которые:
- Не изменяются между окружениями (dev/prod)
- Не являются секретами
- Определяют поведение приложения
"""

# Ограничения интерфейса
MAX_MESSAGE_LENGTH = 4000
MAX_LIBRARY_ITEMS_PER_PAGE = 5

# Тайминги UI (статичные, не настраиваемые)
SEARCH_DELAY_SECONDS = 0.3
TYPING_DELAY_SECONDS = 0.5
API_TIMEOUT_SECONDS = 30

# Валидация пользовательского ввода
MIN_SEARCH_QUERY_LENGTH = 2
MAX_SEARCH_QUERY_LENGTH = 500
MAX_TEXT_INPUT_LENGTH = 1000

# ArXiv API (статичные данные)
ARXIV_API_BASE_URL = "https://export.arxiv.org/api/query"
ARXIV_NAMESPACES = {
    'atom': 'http://www.w3.org/2005/Atom',
    'arxiv': 'http://arxiv.org/schemas/atom'
}

# IEEE API (статичные данные)
IEEE_API_BASE_URL = "https://api.ieee.org/api/v1/search/articles"

# NCBI API (статичные данные)
NCBI_API_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# LLM API (статичные данные)
LLM_API_BASE_URL = "https://openrouter.ai/api/v1"

