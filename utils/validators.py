import re
import html

class InputValidator:
    def __init__(self):
        self.suspicious_patterns = [
            r'@[a-zA-Z0-9_]+',  # Mentions
            r'https?://[^\s]+',  # URLs
            r'#[a-zA-Z0-9_]+',  # Hashtags
            r'[+]?[0-9]{1,3}[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,9}',  # Phone numbers
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b',  # IP addresses
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'  # Email addresses
        ]
        
    def sanitize_text(self, text: str, max_length: int = 1000) -> str:
        if not text:
            return ""
        sanitized = html.escape(text)
        sanitized = re.sub(r'[<>"\']', '', sanitized).strip()
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        return sanitized
    
    def contains_suspicious_content(self, text: str) -> bool:
        if not text:
            return False
        for pattern in self.suspicious_patterns:
            if re.search(pattern, text):
                return True
        return False