import pytest
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from translation_providers import GeminiProvider, OpenAIProvider, TranslationProviderFactory

@pytest.mark.asyncio
class TestGeminiProvider:
    @pytest.fixture
    def provider(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test_key'}):
            return GeminiProvider()

    async def test_translate_text(self, provider):
        with patch('openai.AsyncOpenAI') as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock()
            instance.chat.completions.create.return_value.choices = [
                MagicMock(message=MagicMock(content="Translated text"))
            ]
            
            result = await provider.translate_text("Test text", "vi", "gemini-2.0-flash")
            assert result == "Translated text"
            
            # Verify correct API call
            instance.chat.completions.create.assert_called_once()
            call_args = instance.chat.completions.create.call_args[1]
            assert call_args['model'] == "gemini-2.0-flash"
            assert len(call_args['messages']) == 2
            assert "vi" in call_args['messages'][0]['content']

    def test_missing_api_key(self):
        with patch.dict(os.environ, clear=True):
            provider = GeminiProvider()
            with pytest.raises(ValueError, match="GEMINI_API_KEY.*not set"):
                asyncio.run(provider.translate_text("test", "vi", "gemini-2.0-flash"))

@pytest.mark.asyncio
class TestOpenAIProvider:
    @pytest.fixture
    def provider(self):
        return OpenAIProvider()

    async def test_translate_text(self, provider):
        with patch('openai.AsyncOpenAI') as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock()
            instance.chat.completions.create.return_value.choices = [
                MagicMock(message=MagicMock(content="Translated text"))
            ]
            
            result = await provider.translate_text("Test text", "vi", "gpt-3.5-turbo")
            assert result == "Translated text"
            
            # Verify correct API call
            instance.chat.completions.create.assert_called_once()
            call_args = instance.chat.completions.create.call_args[1]
            assert call_args['model'] == "gpt-3.5-turbo"
            assert len(call_args['messages']) == 2
            assert "vi" in call_args['messages'][0]['content']

class TestTranslationProviderFactory:
    def test_create_gemini_provider(self):
        provider = TranslationProviderFactory.create_provider('gemini')
        assert isinstance(provider, GeminiProvider)

    def test_create_openai_provider(self):
        provider = TranslationProviderFactory.create_provider('openai')
        assert isinstance(provider, OpenAIProvider)

    def test_invalid_provider(self):
        with pytest.raises(ValueError, match="Unknown translation provider"):
            TranslationProviderFactory.create_provider('invalid')