import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from websocket_connection import (
    WebSocketClientConnection,
    WebSocketServerProcessor,
    create_websocket_processor
)
from translation_interfaces import TranslationConfig

@pytest.mark.asyncio
class TestWebSocketClientConnection:
    @pytest.fixture
    def websocket(self):
        return AsyncMock()

    @pytest.fixture
    def connection(self, websocket):
        return WebSocketClientConnection(websocket)

    async def test_send_success(self, connection, websocket):
        message = "test message"
        await connection.send(message)
        websocket.send.assert_called_once_with(message)

    async def test_send_connection_closed(self, connection, websocket):
        websocket.send.side_effect = Exception("Connection closed")
        await connection.send("test")  # Should handle exception gracefully

    async def test_receive_audio_binary(self, connection, websocket):
        test_data = b"test audio data"
        websocket.recv.return_value = test_data
        result = await connection.non_blocking_receive_audio()
        assert result == test_data

    async def test_receive_audio_json(self, connection, websocket):
        test_audio = b"test audio data"
        websocket.recv.return_value = json.dumps({"audio": test_audio.hex()})
        result = await connection.non_blocking_receive_audio()
        assert isinstance(result, bytes)

@pytest.mark.asyncio
class TestWebSocketServerProcessor:
    @pytest.fixture
    def websocket(self):
        return AsyncMock()

    @pytest.fixture
    def online_asr_proc(self):
        mock = MagicMock()
        mock.init = MagicMock()
        mock.process_iter.return_value = (0.0, 1.0, "test transcript")
        return mock

    @pytest.fixture
    def processor(self, websocket, online_asr_proc):
        return WebSocketServerProcessor(websocket, online_asr_proc, min_chunk=0.1)

    async def test_send_result(self, processor):
        transcript = (0.0, 1.0, "test transcript")
        await processor.send_result(transcript)
        
        # Verify JSON message format
        websocket = processor.connection.websocket
        assert websocket.send.called
        call_args = websocket.send.call_args[0][0]
        message = json.loads(call_args)
        assert message["type"] == "transcription"
        assert message["text"] == "test transcript"
        assert "start" in message
        assert "end" in message

    async def test_process_async(self, processor):
        # Mock receive_audio_chunk_async to return None after first iteration
        processor.receive_audio_chunk_async = AsyncMock()
        processor.receive_audio_chunk_async.side_effect = [
            bytes([1, 2, 3]),  # First call returns some audio data
            None  # Second call returns None to end the loop
        ]
        
        await processor.process_async()
        
        # Verify ASR processor was initialized and used
        processor.online_asr_proc.init.assert_called_once()
        processor.online_asr_proc.insert_audio_chunk.assert_called_once()
        processor.online_asr_proc.process_iter.assert_called_once()

class TestCreateWebSocketProcessor:
    @pytest.fixture
    def websocket(self):
        return AsyncMock()

    @pytest.fixture
    def online_asr_proc(self):
        return MagicMock()

    def test_create_without_translation(self, websocket, online_asr_proc):
        processor = create_websocket_processor(
            websocket=websocket,
            online_asr_proc=online_asr_proc,
            min_chunk=0.1
        )
        assert isinstance(processor, WebSocketServerProcessor)

    def test_create_with_translation(self, websocket, online_asr_proc):
        translation_config = TranslationConfig(
            target_language="vi",
            model="gemini-2.0-flash",
            provider="gemini"
        )
        processor = create_websocket_processor(
            websocket=websocket,
            online_asr_proc=online_asr_proc,
            min_chunk=0.1,
            translation_config=translation_config
        )
        from server_processors import TranslatedServerProcessor
        assert isinstance(processor, TranslatedServerProcessor)