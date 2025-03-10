from abc import ABC, abstractmethod
from typing import Optional, List, Tuple, Dict

class TranslationProvider(ABC):
    """Abstract base class for translation providers"""
    
    @abstractmethod
    async def translate_text(self, text: str, target_language: str, model: str) -> str:
        """Translate text to target language using specified model"""
        pass

class TranslationResult:
    """Data class for translation results"""
    def __init__(self, original: str, translated: str, start_time: float, end_time: float):
        self.original = original
        self.translated = translated
        self.start_time = start_time
        self.end_time = end_time

class TranslationConfig:
    """Configuration for translation settings"""
    def __init__(self, 
                 target_language: str = 'en',
                 model: str = 'gemini-2.0-flash',
                 provider: str = 'gemini',
                 interval: float = 3.0,
                 max_buffer_time: float = 10.0,
                 min_text_length: int = 20,
                 inactivity_timeout: float = 2.0,
                 system_prompt: Optional[str] = None):
        self.target_language = target_language
        self.model = model
        self.provider = provider
        self.interval = interval
        self.max_buffer_time = max_buffer_time
        self.min_text_length = min_text_length
        self.inactivity_timeout = inactivity_timeout
        self.system_prompt = system_prompt