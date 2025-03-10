import os
import logging
import openai
import asyncio
from typing import Optional, List, Tuple
from translation_interfaces import TranslationProvider

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = "Translate the following text to {target_language}"

class BaseTranslationProvider(TranslationProvider):
    """Base class for translation providers"""

    def __init__(self):
        self.client = None

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
                "vi": "Vietnamese",
                # Add more mappings as needed
            }
            return language_map.get(language_code, language_code)
    
    async def _execute_with_retry(self, func, *args, **kwargs):
        """Execute a function with retry logic for 5xx errors"""
        max_retries = 3
        retry_delay = 1  # Initial delay in seconds
        
        for attempt in range(max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except (openai.InternalServerError, openai.APITimeoutError) as e:
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"API server error (5xx). Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                # Either not a 5xx error or we've exhausted retries
                raise
    
    async def translate_text(self, text: str, target_language: str, model: str, system_prompt: Optional[str] = None, history: Optional[List[Tuple[str, str]]] = None) -> str:
        """Common implementation of translate_text with optional history context"""
        self._validate_api_key()
        
        prompt = system_prompt if system_prompt else DEFAULT_PROMPT
        prompt = prompt.format(target_language=self._get_target_language(target_language))
        
        messages = [
            {"role": "system", "content": prompt}
        ]
        
        # Add historical context if available
        if history and len(history) > 0:
            messages.append({
                "role": "user", 
                "content": "Below are previously translated segments for context. Use them to maintain consistency in your translations:\n\n" + 
                           "\n\n".join([f"Original: {orig}\nTranslation: {trans}" for orig, trans in history])
            })
            messages.append({"role": "assistant", "content": "I'll use these previous translations to maintain consistency."})
        
        # Add current text to translate
        messages.append({"role": "user", "content": text})
        
        async def make_api_call():
            return await self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1000
            )
        
        response = await self._execute_with_retry(make_api_call)
        return response.choices[0].message.content.strip()
    
    def _validate_api_key(self):
        """Validate that API key is set"""
        pass  # Default implementation does nothing, override if needed

class GeminiProvider(BaseTranslationProvider):
    """Gemini API translation provider"""
    
    def __init__(self):
        super().__init__()
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
        super().__init__()
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