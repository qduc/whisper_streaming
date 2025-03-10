import os
import logging
import openai
from typing import Optional
from translation_interfaces import TranslationProvider

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = "Translate the following text to {target_language}"

class GeminiProvider(TranslationProvider):
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
            
    async def translate_text(self, text: str, target_language: str, model: str, system_prompt: Optional[str] = None) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
            
        prompt = system_prompt if system_prompt else DEFAULT_PROMPT.format(target_language=target_language)
        response = await self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=1000
        )
        
        return response.choices[0].message.content.strip()

class OpenAIProvider(TranslationProvider):
    """OpenAI API translation provider"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI()
        
    async def translate_text(self, text: str, target_language: str, model: str, system_prompt: Optional[str] = None) -> str:
        prompt = system_prompt if system_prompt else DEFAULT_PROMPT.format(target_language=target_language)
        response = await self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=1000
        )
        
        return response.choices[0].message.content.strip()

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