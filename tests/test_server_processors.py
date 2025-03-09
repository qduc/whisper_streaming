import pytest
import json
import asyncio
import time
from unittest.mock import MagicMock, patch
from server_processors import (
    TranslationProcessor,
    process_translation,
    ServerProcessor,
    TranslatedServerProcessor
)
from translation_utils import TranslationManager

class MockConnection:
    def __init__(self):
        self.sent_messages = []
        
    async def send(self, message):
        self.sent_messages.append(message)

class TestTranslationProcessor:
    @pytest.fixture
    def translation_manager(self):
        return MagicMock(spec=TranslationManager)
        
    @pytest.fixture
    def processor(self, translation_manager):
        return TranslationProcessor(translation_manager, min_text_length=20)
    
    def test_calculate_adaptive_min_length_no_history(self, processor):
        assert processor.calculate_adaptive_min_length() == 20
        
    def test_calculate_adaptive_min_length_with_history(self, processor):
        processor.translation_manager.translation_history = [("Hello world", "Hola mundo")]
        length = processor.calculate_adaptive_min_length()
        assert 10 <= length <= 30  # Should be within reasonable bounds
        
    def test_should_translate_short_text(self, processor):
        assert not processor.should_translate("short", 1.0, 4.0, 5.0)
        
    def test_should_translate_timeout(self, processor):
        assert processor.should_translate("long enough text here", 6.0, 4.0, 5.0)

@pytest.mark.asyncio
class TestProcessTranslation:
    @pytest.fixture
    def connection(self):
        return MockConnection()
        
    @pytest.fixture
    def translation_manager(self):
        manager = MagicMock(spec=TranslationManager)
        manager.translate_text_async.return_value = "translated text"
        return manager
    
    async def test_process_translation_basic(self, connection, translation_manager):
        text_buffer = []
        last_translation_time = 0
        
        await process_translation(
            connection=connection,
            text="test text",
            text_buffer=text_buffer,
            last_translation_time=last_translation_time,
            translation_manager=translation_manager
        )
        
        assert len(text_buffer) == 1
        assert text_buffer[0] == "test text"

@pytest.mark.asyncio
class TestTranslatedServerProcessor:
    @pytest.fixture
    def connection(self):
        return MockConnection()
        
    @pytest.fixture
    def online_asr_proc(self):
        proc = MagicMock()
        proc.process_iter.return_value = (0.0, 1.0, "test text")
        return proc
    
    async def test_send_result(self, connection, online_asr_proc):
        # Create a mock translation manager
        translation_manager = MagicMock(spec=TranslationManager)
        
        processor = TranslatedServerProcessor(
            connection,
            online_asr_proc,
            min_chunk=0.1
        )
        processor.translation_manager = translation_manager  # Set the translation manager manually
        
        await processor.send_result((0.0, 1.0, "test text"))
        
    async def test_translate_buffer(self, connection, online_asr_proc):
        # Create a mock translation manager
        translation_manager = MagicMock(spec=TranslationManager)
        # Set up the async mock to return a value that can be awaited
        translation_manager.translate_text_async = MagicMock(return_value=asyncio.Future())
        translation_manager.translate_text_async.return_value.set_result("Hola mundo")
        
        processor = TranslatedServerProcessor(
            connection,
            online_asr_proc,
            min_chunk=0.1
        )
        processor.translation_manager = translation_manager  # Set the translation manager after initialization
        
        processor.text_buffer = ["Hello", "world"]
        processor.time_buffer = [(0.0, 0.5), (0.5, 1.0)]
        # You already set up the mock correctly above, no need to overwrite it
        
        results = await processor.translate_buffer()
        assert len(results) == 1
        assert results[0][2] == "Hola mundo"  # Check translation

@pytest.mark.asyncio
class TestServerProcessor:
    @pytest.fixture
    def connection(self):
        return MockConnection()
        
    @pytest.fixture
    def online_asr_proc(self):
        return MagicMock()
        
    async def test_send_websocket(self, connection, online_asr_proc):
        processor = ServerProcessor(connection, online_asr_proc, min_chunk=0.1)
        await processor.send_websocket("0.0 1.0 test message")
        
        sent_msg = json.loads(connection.sent_messages[0])
        assert sent_msg["type"] == "transcription"
        assert sent_msg["text"] == "test message"
        assert sent_msg["start"] == 0.0
        assert sent_msg["end"] == 1.0

@pytest.mark.asyncio
class TestTranslatedServerProcessorExtended:
    @pytest.fixture
    def connection(self):
        return MockConnection()
        
    @pytest.fixture 
    def online_asr_proc(self):
        return MagicMock()

    @pytest.fixture
    def processor(self, connection, online_asr_proc):
        proc = TranslatedServerProcessor(
            connection,
            online_asr_proc, 
            min_chunk=0.1,
            target_language="es",
            translation_interval=2.0
        )
        # Mock the translation manager
        proc.translation_manager = MagicMock()
        return proc
    
    async def test_should_translate_buffer(self, processor):
        processor.text_buffer = ["This is a", "test message"]
        processor.time_buffer = [(0.0, 1.0), (1.0, 2.0)]
        processor.last_translation_time = time.time() - 5.0  # Force timeout
        
        assert processor.should_translate_buffer() == True
        
    async def test_partial_translate_buffer(self, processor):
        processor.text_buffer = ["This is a test.", "Still processing..."]
        processor.time_buffer = [(0.0, 1.0), (1.0, 2.0)]
        processor.translation_manager.translate_text_async.return_value = "Esta es una prueba."
        
        results = await processor.partial_translate_buffer()
        
        assert len(results) == 1
        assert results[0][2] == "Esta es una prueba."
        assert processor.text_buffer == ["Still processing..."]
        
    async def test_check_inactivity_timeout(self, processor):
        processor.text_buffer = ["This is a test"]
        processor.time_buffer = [(0.0, 1.0)]
        processor.last_text_time = time.time() - processor.inactivity_timeout - 1
        processor.translation_manager.translate_text_async.return_value = "Esta es una prueba"
        
        result = await processor.check_inactivity_timeout()
        
        assert result == True
        assert len(processor.text_buffer) == 0
        
    async def test_process_error_handling(self, processor):
        processor.receive_audio_chunk = MagicMock(side_effect=Exception("Test error"))
        
        with pytest.raises(Exception) as exc_info:
            await processor.process()
        assert str(exc_info.value) == "Test error"

@pytest.mark.asyncio        
class TestProcessTranslationExtended:
    @pytest.fixture
    def connection(self):
        return MockConnection()
        
    @pytest.fixture
    def translation_manager(self):
        manager = MagicMock(spec=TranslationManager)
        manager.translate_text_async.return_value = "translated text"
        return manager

    async def test_process_translation_with_different_languages(self, connection, translation_manager):
        for lang in ['es', 'fr', 'de']:
            text_buffer = []
            last_translation_time = time.time() - 10  # Force translation
            
            await process_translation(
                connection=connection,
                text="test text",
                text_buffer=text_buffer,
                last_translation_time=last_translation_time,
                target_language=lang,
                translation_manager=translation_manager
            )
            
            translation_manager.translate_text_async.assert_called()
            
    async def test_process_translation_error_handling(self, connection):
        text_buffer = []
        last_translation_time = 0
        
        # Test with broken connection
        connection.send = MagicMock(side_effect=Exception("Connection error"))
        
        await process_translation(
            connection=connection,
            text="test text",
            text_buffer=text_buffer,
            last_translation_time=last_translation_time
        )
        
        assert len(text_buffer) == 1  # Should still buffer text despite error
