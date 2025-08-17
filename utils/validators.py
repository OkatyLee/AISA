import re
import html
from typing import Optional

class InputValidator:
    """
    Класс для валидации и санитизации пользовательского ввода
    
    Обеспечивает безопасность и качество входных данных
    """
    
    def __init__(self):
        # Паттерны потенциально подозрительного контента
        self.suspicious_patterns = [
            r'@[a-zA-Z0-9_]+',  # Mentions
            r'https?://[^\s]+',  # URLs (кроме научных)
            r'#[a-zA-Z0-9_]+',  # Hashtags
            #r'[+]?[0-9]{1,3}[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,9}',  # Phone numbers
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b',  # IP addresses
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'  # Email addresses
        ]
        
        # Разрешенные научные URL
        self.allowed_domains = [
            'arxiv.org',
            'scholar.google.com',
            'pubmed.ncbi.nlm.nih.gov',
            'doi.org',
            'semanticscholar.org',
            'ieee.org'
        ]
        
    def sanitize_text(self, text: str, max_length: int = 1000) -> str:
        """
        Санитизация текста от потенциально опасных символов
        
        Args:
            text: Исходный текст
            max_length: Максимальная длина текста
            
        Returns:
            Очищенный текст
        """
        if not text:
            return ""
            
        # HTML escape для безопасности
        sanitized = html.escape(text)
        
        # Удаляем потенциально опасные символы
        sanitized = re.sub(r'[<>"\'\`]', '', sanitized)
        
        # Нормализуем пробелы
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        # Ограничиваем длину
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
            
        return sanitized
    
    def contains_suspicious_content(self, text: str) -> bool:
        """
        Проверка на подозрительный контент
        
        Args:
            text: Текст для проверки
            
        Returns:
            True если найден подозрительный контент
        """
        if not text:
            return False
            
        for pattern in self.suspicious_patterns:
            if re.search(pattern, text):
                # Дополнительная проверка для URL
                if 'http' in pattern and self._is_allowed_url(text):
                    continue
                return True
                
        return False
    
    def _is_allowed_url(self, text: str) -> bool:
        """Проверка разрешенных научных URL"""
        for domain in self.allowed_domains:
            if domain in text.lower():
                return True
        return False
    
    def validate_search_query(self, query: str) -> tuple[bool, Optional[str]]:
        """
        Валидация поискового запроса
        
        Args:
            query: Поисковый запрос
            
        Returns:
            Tuple (is_valid, error_message)
        """
        if not query or not query.strip():
            return False, "Запрос не может быть пустым"
            
        if len(query.strip()) < 2:
            return False, "Запрос слишком короткий (минимум 2 символа)"
            
        if len(query) > 500:
            return False, "Запрос слишком длинный (максимум 500 символов)"
            
        # Проверка на спам (много повторяющихся символов)
        if re.search(r'(.)\1{5,}', query):
            return False, "Запрос содержит слишком много повторяющихся символов"
            
        return True, None
    
    def clean_search_query(self, query: str) -> str:
        """
        Очистка поискового запроса для ArXiv API
        
        Args:
            query: Исходный запрос
            
        Returns:
            Очищенный запрос
        """
        # Удаляем команду /search если осталась
        query = re.sub(r'^/search\s*', '', query, flags=re.IGNORECASE)
        
        # Санитизируем
        query = self.sanitize_text(query)
        
        # Удаляем лишние символы для ArXiv
        query = re.sub(r'[^\w\s\-\.]', ' ', query)
        
        # Нормализуем пробелы
        query = re.sub(r'\s+', ' ', query).strip()
        
        return query
    
    def escape_markdown(self, text: str) -> str:
        """
        Экранирование специальных символов Markdown
        
        Args:
            text: Исходный текст
            
        Returns:
            Экранированный текст
        """
        MDV2_SPECIALS = r"_*\[\]()~`>#+\-=|{}.!\\"
        
        # Разделяем текст на сегменты: обычный текст и блоки кода
        parts = re.split(r'(```.*?```|`.*?`)', text, flags=re.DOTALL)
        escaped_parts = []

        for part in parts:
            if part.startswith("```") and part.endswith("```"):
                # Блок кода трогаем только для экранирования backslash
                escaped_parts.append(part.replace("\\", "\\\\"))
            elif part.startswith("`") and part.endswith("`"):
                # Inline code — аналогично
                escaped_parts.append(part.replace("\\", "\\\\"))
            else:
                # Обычный текст — экранируем все специальные символы
                escaped_parts.append(re.sub(f"([{re.escape(MDV2_SPECIALS)}])", r"\\\1", part))

        return "".join(escaped_parts)