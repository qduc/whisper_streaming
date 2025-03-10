import asyncio
import websockets
import io
import json
import logging
import numpy as np
import soundfile
import librosa
import base64
from server_base import BaseServerProcessor
from translation_interfaces import TranslationConfig, TranslationProvider
from translation_utils import TranslationManager
from server_processors import ConnectionInterface

logger = logging.getLogger(__name__)

class WebSocketConnection:
    """WebSocket server that manages connections"""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
    
    def run(self, handler_function):
        """Run the WebSocket server with the provided handler function"""
        async def start_server():
            async with websockets.serve(handler_function, self.host, self.port):
                logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")
                await asyncio.Future()
        
        try:
            asyncio.run(start_server())
        except KeyboardInterrupt:
            logger.info("Server stopped by user")

class WebSocketClientConnection(ConnectionInterface):
    """WebSocket connection adapter implementing ConnectionInterface"""
    def __init__(self, websocket):
        self.websocket = websocket
        self.buffer = b''

        # Setup ping handler if possible
        if hasattr(websocket, 'ping_handler'):
            original_ping = websocket.ping_handler
            websocket.ping_handler = self._ping_handler_wrapper(original_ping)
    
    def _ping_handler_wrapper(self, original_handler):
        """Wrap the original ping handler to add logging"""
        async def wrapped_ping_handler(ping):
            logger.debug(f"Received ping: {ping.decode('utf-8', errors='replace') if isinstance(ping, bytes) else ping}")
            return await original_handler(ping)
        return wrapped_ping_handler
    
    async def send(self, message: str) -> None:
        """Send response back to the client"""
        try:
            await self.websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Unable to send message - connection closed")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    
    async def non_blocking_receive_audio(self):
        """Receive audio data from WebSocket"""
        try:
            message = await self.websocket.recv()
            
            if isinstance(message, bytes):
                return message
                
            try:
                data = json.loads(message)
                if 'audio' in data:
                    return base64.b64decode(data['audio'])
                return b''
            except json.JSONDecodeError:
                logger.warning("Received message is neither binary nor valid JSON")
                return b''
                
        except websockets.exceptions.ConnectionClosed:
            return b''
    
    def is_closed(self) -> bool:
        """Check if the WebSocket connection is closed"""
        return self.websocket.closed if hasattr(self.websocket, 'closed') else self.websocket.state.name == 'CLOSED'

class WebSocketServerProcessor(BaseServerProcessor):
    """WebSocket implementation of the server processor"""
    
    def __init__(self, websocket, online_asr_proc, min_chunk=0.1):
        connection = WebSocketClientConnection(websocket)
        super().__init__(connection, online_asr_proc, min_chunk)
    
    async def send_result(self, transcript):
        """Send transcription result to client as JSON"""
        if transcript and transcript[0] is not None:
            beg, end = transcript[0]*1000, transcript[1]*1000
            if self.last_end is not None:
                beg = max(beg, self.last_end)
            self.last_end = end
            
            text = transcript[2].replace("  ", " ")
            logger.debug(f"Transcript {beg}-{end}: {text}")
            
            msg = json.dumps({
                "type": "transcription",
                "start": beg,
                "end": end,
                "text": text
            })
            
            await self.connection.send(msg)
    
    async def process_async(self):
        """Asynchronous processing loop"""
        self.online_asr_proc.init()
        try:
            while True:
                a = await self.receive_audio_chunk_async()
                if a is None:
                    break
                self.online_asr_proc.insert_audio_chunk(a)
                o = self.online_asr_proc.process_iter()
                try:
                    await self.send_result(o)
                except Exception as e:
                    logger.error(f"Connection error: {e}")
                    break
        except Exception as e:
            logger.error(f"Error in processor: {e}")
            raise
    
    async def receive_audio_chunk_async(self):
        """Async version of receive_audio_chunk"""
        out = []
        minlimit = self.min_chunk * self.SAMPLING_RATE
        while sum(len(x) for x in out) < minlimit:
            # Get raw bytes using the await keyword explicitly
            raw_bytes = await self.connection.non_blocking_receive_audio()
            if not raw_bytes:
                break
            
            # Process the bytes
            sf = soundfile.SoundFile(io.BytesIO(raw_bytes), channels=1, endian="LITTLE",
                                    samplerate=self.SAMPLING_RATE, subtype="PCM_16", format="RAW")
            audio, _ = librosa.load(sf, sr=self.SAMPLING_RATE, dtype=np.float32)
            out.append(audio)
            
        if not out:
            return None
        conc = np.concatenate(out)
        if self.is_first and len(conc) < minlimit:
            return None
        self.is_first = False
        return np.concatenate(out)

def create_websocket_processor(websocket, online_asr_proc, min_chunk, translation_config=None):
    """Factory function to create appropriate WebSocket processor"""
    if translation_config:
        from server_processors import TranslatedServerProcessor
        connection = WebSocketClientConnection(websocket)
        return TranslatedServerProcessor(
            connection=connection,
            online_asr_proc=online_asr_proc,
            min_chunk=min_chunk,
            translation_config=translation_config
        )
    else:
        return WebSocketServerProcessor(websocket, online_asr_proc, min_chunk)

async def handle_connection(websocket, online_asr_factory):
    """Handle a WebSocket connection"""
    logger.info(f"New WebSocket connection established: {websocket.remote_address}")
    
    try:
        # Create an instance of the online ASR processor
        online_asr_proc = online_asr_factory()
        
        # Create WebSocket server processor
        processor = WebSocketServerProcessor(websocket, online_asr_proc)
        
        # Process the audio stream
        await processor.process_async()
        
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"WebSocket connection closed: {websocket.remote_address}")
    except Exception as e:
        logger.error(f"Error handling WebSocket connection: {e}")
        await websocket.close(1011, f"Server error: {str(e)}")

async def start_server(host, port, online_asr_factory):
    """Start WebSocket server"""
    async def connection_handler(websocket, path):
        await handle_connection(websocket, online_asr_factory)
        
    server = await websockets.serve(connection_handler, host, port, ping_interval=20, ping_timeout=10)
    
    # Keep the server running
    await server.wait_closed()

def run_websocket_server(host="0.0.0.0", port=8765, online_asr_factory=None):
    """Run the WebSocket server with the provided ASR processor factory"""
    if online_asr_factory is None:
        raise ValueError("You must provide a factory function that creates an online ASR processor")
    
    # Start the WebSocket server
    asyncio.run(start_server(host, port, online_asr_factory))