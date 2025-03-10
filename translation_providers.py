import os
import logging
import openai
from typing import Optional
from translation_interfaces import TranslationProvider

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = "Translate the following text to {target_language}"

class BaseTranslationProvider(TranslationProvider):
    """Base class for translation providers"""
    
    def _get_target_language(self, language_code: str) -> str:
        """Convert language code to target language"""
        try:
            # Using langcodes library if available
            import langcodes
            return langcodes.Language.get(language_code).display_name()
        except (ImportError, AttributeError, KeyError):
            # Fallback to existing manual mapping
            language_map = {
                "en": "English",
                "es": "Spanish",
                "fr": "French",
                "de": "German",
                "zh": "Chinese",
                # Add more mappings as needed
            }
            return language_map.get(language_code, language_code)
    
    async def translate_text(self, text: str, target_language: str, model: str, system_prompt: Optional[str] = None) -> str:
        """Common implementation of translate_text"""
        self._validate_api_key()
        
        prompt = system_prompt if system_prompt else DEFAULT_PROMPT
        prompt = prompt.format(target_language=self._get_target_language(target_language))
        response = await self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=1000
        )
        
        return response.choices[0].message.content.strip()
    
    def _validate_api_key(self):
        """Validate that API key is set"""
        pass  # Default implementation does nothing, override if needed

class GeminiProvider(BaseTranslationProvider):
    """Gemini API translation provider"""
    
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY environment variable not set")
        else:
            self.client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
    
    def _validate_api_key(self):
        """Validate Gemini API key"""
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

class OpenAIProvider(BaseTranslationProvider):
    """OpenAI API translation provider"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI()

class TranslationProviderFactory:
    """Factory for creating translation providers"""
    
    @staticmethod
    def create_provider(provider_type: str) -> TranslationProvider:
        if provider_type == 'gemini':
            return GeminiProvider()
        elif provider_type == 'openai':
            return OpenAIProvider()
        else:
            raise ValueError(f"Unknown translation provider: {provider_type}")