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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSocketConnection:
    """WebSocket server that manages connections"""
    def __init__(self, host, port):
        self.host = host
        self.port = port
    
    def run(self, handler_function):
        """Run the WebSocket server with the provided handler function
        
        Args:
            handler_function: Async function that takes a websocket connection
        """
        async def start_server():
            async with websockets.serve(handler_function, self.host, self.port):
                logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")
                # Keep the server running until interrupted
                await asyncio.Future()
        
        try:
            asyncio.run(start_server())
        except KeyboardInterrupt:
            logger.info("Server stopped by user")

class WebSocketClientConnection:
    """WebSocket connection adapter for the BaseServerProcessor"""
    def __init__(self, websocket):
        self.websocket = websocket
        self.buffer = b''
    
    async def non_blocking_receive_audio(self):
        """Receive audio data from WebSocket"""
        try:
            # Receive message from WebSocket
            message = await self.websocket.recv()
            
            # Check if the message is a JSON object with audio data
            try:
                data = json.loads(message)
                if 'audio' in data:
                    # Decode base64 audio
                    return base64.b64decode(data['audio'])
            except json.JSONDecodeError:
                # If not JSON, assume raw binary data
                return message
                
            return b''
        except websockets.exceptions.ConnectionClosed:
            return b''
    
    async def send(self, message):
        """Send response back to the client"""
        await self.websocket.send(json.dumps({"transcript": message}))

class WebSocketServerProcessor(BaseServerProcessor):
    """WebSocket implementation of the server processor"""
    
    def __init__(self, websocket, online_asr_proc, min_chunk=0.1):
        connection = WebSocketClientConnection(websocket)
        super().__init__(connection, online_asr_proc, min_chunk)
    
    async def send_result(self, transcript):
        """Send transcription result to client"""
        if transcript:
            formatted_transcript = self.format_output_transcript(transcript)
            if formatted_transcript:
                await self.connection.send(formatted_transcript)
    
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
                    logger.info(f"Connection error: {e}")
                    break
        except Exception as e:
            logger.error(f"Error in processor: {e}")
            raise
    
    async def receive_audio_chunk_async(self):
        """Async version of receive_audio_chunk"""
        out = []
        minlimit = self.min_chunk * self.SAMPLING_RATE
        while sum(len(x) for x in out) < minlimit:
            raw_bytes = await self.connection.non_blocking_receive_audio()
            if not raw_bytes:
                break
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
        
    server = await websockets.serve(connection_handler, host, port)
    logger.info(f"WebSocket server started on ws://{host}:{port}")
    
    # Keep the server running
    await server.wait_closed()

def run_websocket_server(host="0.0.0.0", port=8765, online_asr_factory=None):
    """Run the WebSocket server with the provided ASR processor factory"""
    if online_asr_factory is None:
        raise ValueError("You must provide a factory function that creates an online ASR processor")
    
    # Start the WebSocket server
    asyncio.run(start_server(host, port, online_asr_factory))