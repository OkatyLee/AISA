from enum import Enum
from os import altsep
import re
from typing import Dict, List, Tuple
import numpy as np
from attr import dataclass
from utils.nlu.intents import Intent, IntentResult

class RuleBasedIntentClassifier:
    """
    Классификатор намерений на основе правил.
    """
    
    def __init__(self):
        self.patterns = {
            Intent.SEARCH: [
                r"найд[иу]|поищ[иу]|ищ[ую]|search|что есть по|статьи про",
                r"хочу найти|нужны статьи|поиск.*по|что нового.*в области",
                r"еще статьи|больше статей|дополнительно|также",
                r"от автора|автор[а-я]*\s+[А-Я]|from author|by\s+[A-Z]",
                r"за.*год|в.*году|year.*\d{4}",
                r"больше информации|дополнительные данные|еще.*результат"
            ],
            Intent.SAVE_ARTICLE: [
                r"сохрани|добавь.*избранное|запомни|save|в закладки",
                r"хочу сохранить|добавить.*список"
            ],
            Intent.LIST_SAVED: [
                r"мои статьи|что сохранено|покажи.*список|saved articles|покажи.*мои",
                r"мои закладки|сохраненные статьи|что у меня есть|мои сохранен"
            ],
            Intent.GET_SUMMARY: [
                r"расскажи про|что это|объясни|резюме|summary|краткое содержание",
                r"в чем суть|основная идея|о чем статья"
            ],
            Intent.HELP: [
                r"помощь|help|как.*работать|что.*умеешь|команды",
                r"не понимаю|как пользоваться"
            ],
            Intent.GREETING: [
                r"привет|hello|hi|здравствуй|добро утро|добрый день|добрый вечер",
                r"как дела|начнем|давай начнем|готов работать"
            ]
        }
        self.compiled_patterns: Dict[Intent, List[re.Pattern]] = {}
        for intent, patterns in self.patterns.items():
            self.compiled_patterns[intent] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]
            
    def classify(self, text: str, context_intent: Intent = None) -> IntentResult:
        """
        Классификация текста на основе правил с учетом контекста.
        
        Args:
            text: Входной текст
            context_intent: Предыдущее намерение из контекста
            
        Returns:
            IntentResult с определенным намерением и уверенностью
        """
        text = text.strip()
        
        scores = {}
        for intent, patterns in self.compiled_patterns.items():
            score = 0.0
            for pattern in patterns:
                matches = pattern.findall(text)
                if matches:
                    score += len(matches) * 0.5  # Каждое совпадение увеличивает уверенность
            if score > 0:
                scores[intent] = score

        # Если ничего не найдено, но есть контекст и текст короткий (возможно уточнение)
        if not scores and context_intent and len(text.split()) <= 5:
            if context_intent == Intent.SEARCH:
                # Короткие фразы в контексте поиска считаем продолжением поиска
                scores[Intent.SEARCH] = 0.3

        if not scores:
            return IntentResult(Intent.UNKNOWN, 0.0, [])

        sorted_keys, sorted_scores = zip(*sorted(scores.items(), key=lambda x: x[1], reverse=True))
        sorted_scores = np.array(sorted_scores)
        sorted_scores = np.exp(sorted_scores) / np.sum(np.exp(sorted_scores))  # Нормализация с использованием softmax
        best_intent = sorted_keys[0]
        best_score = sorted_scores[0]
        alternatives = [
            (intent, score) for intent, score in zip(sorted_keys[1:3], sorted_scores[1:3])
        ]   
        
        return IntentResult(best_intent, best_score, alternatives)
    
class MLIntentClassifier:
    """
    Заглушка для ML-классификатора.
    TODO: В реальном приложении здесь будет интеграция с ML-моделью.
    """
    
    def classify(self, text: str) -> IntentResult:
        # Здесь должна быть логика ML-классификации
        # Для примера просто возвращаем UNKNOWN
        return IntentResult(Intent.UNKNOWN, 0.0, [])
    
