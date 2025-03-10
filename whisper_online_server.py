#!/usr/bin/env python3
from whisper_online import *
import sys
import argparse
import os
import logging
import socket
import yaml
import time
from server_base import Connection, BaseServerProcessor
from server_processors import ServerProcessor, TranslatedServerProcessor
from translation_interfaces import TranslationConfig, TranslationProvider
from translation_providers import TranslationProviderFactory
from websocket_connection import create_websocket_processor, WebSocketConnection, WebSocketClientConnection

logger = logging.getLogger(__name__)

class ServerConfig:
    """Server configuration container"""
    def __init__(self, args, config_file=None):
        self.host = args.host
        self.port = args.port
        self.websocket = args.websocket
        self.warmup_file = args.warmup_file
        
        # Load and merge with YAML config
        yaml_config = load_config(config_file or args.config)
        translation_config = self._create_translation_config(args, yaml_config)
        self.translation_config = translation_config if args.translate else None

        logger.info("Loaded config:")
        # Log translation configuration if enabled
        if self.translation_config:
            logger.info(f"Translation enabled:")
            logger.info(f"  - Target language: {self.translation_config.target_language}")
            logger.info(f"  - Provider: {self.translation_config.provider}")
            logger.info(f"  - Model: {self.translation_config.model}")
            logger.info(f"  - Interval: {self.translation_config.interval} seconds")
            logger.info(f"  - Max buffer time: {self.translation_config.max_buffer_time} seconds")
            logger.info(f"  - Min text length: {self.translation_config.min_text_length} characters")
            logger.info(f"  - Inactivity timeout: {self.translation_config.inactivity_timeout} seconds")
            logger.info(f"  - System prompt: {self.translation_config.system_prompt}")
        else:
            logger.info("Translation disabled")
        
        # ASR config
        self.asr_args = args
        
    def _create_translation_config(self, args, yaml_config) -> TranslationConfig:
        """Create translation config from args and YAML"""
        config = yaml_config.get('translation', {})
        return TranslationConfig(
            target_language=args.target_language or config.get('target_language', 'en'),
            model=args.translation_model or config.get('model', 'gemini-2.0-flash'),
            provider=args.translation_provider or config.get('provider', 'gemini'),
            interval=args.translation_interval or config.get('interval', 3.0),
            max_buffer_time=args.max_buffer_time or config.get('max_buffer_time', 10.0),
            min_text_length=args.min_text_length or config.get('min_text_length', 20),
            inactivity_timeout=args.inactivity_timeout or config.get('inactivity_timeout', 2.0),
            system_prompt=config.get('system_prompt')
        )

def load_config(config_path: str) -> dict:
    """Load configuration from YAML file"""
    if not os.path.exists(config_path):
        logger.warning(f"Config file {config_path} not found. Using default settings.")
        return {"translation": {}}
        
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Error loading config from {config_path}: {e}")
        return {"translation": {}}

def create_asr_processor(args, warmup: bool = True):
    """Create and initialize ASR processor"""
    asr, online = asr_factory(args)
    if warmup:
        warmup_asr(args, asr)
    return online

def warmup_asr(args, asr):
    """Warm up ASR model with sample audio to reduce first-inference latency"""
    if args.warmup_file and os.path.exists(args.warmup_file):
        logger.info(f"Warming up ASR model with {args.warmup_file}")
        try:
            # Load audio file for warmup
            import wave
            import numpy as np
            
            with wave.open(args.warmup_file, 'rb') as wf:
                frames = wf.readframes(wf.getnframes())
                audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Run a single inference to warm up the model
            # The result is ignored since we only want to warm up the model
            _ = asr.transcribe(audio_data)
            logger.info("ASR model warmup completed successfully")
        except Exception as e:
            logger.warning(f"ASR warmup failed: {e}")
    else:
        if args.warmup_file:
            logger.warning(f"Warmup file not found: {args.warmup_file}")
        logger.info("Skipping ASR model warmup (no file specified)")

class Server:
    """Main server class that handles connections and processing"""
    def __init__(self, config: ServerConfig):
        self.config = config
        self.online_asr = None
        
    def _create_processor(self, connection) -> BaseServerProcessor:
        """Create appropriate processor based on configuration"""
        if self.config.translation_config:
            logger.info(f"Translation enabled using provider {self.config.translation_config.provider}, model {self.config.translation_config.model}")
            logger.info(f"Target language: {self.config.translation_config.target_language}")
            logger.info(f"System prompt: {self.config.translation_config.system_prompt}")
            return TranslatedServerProcessor(
                connection=connection,
                online_asr_proc=self.online_asr,
                min_chunk=self.config.asr_args.min_chunk_size,
                translation_config=self.config.translation_config
            )
        else:
            return ServerProcessor(
                connection=connection,
                online_asr_proc=self.online_asr,
                min_chunk=self.config.asr_args.min_chunk_size
            )
            
    def initialize(self):
        """Initialize ASR and server components"""
        self.online_asr = create_asr_processor(self.config.asr_args)
        
    def run_websocket(self):
        """Run WebSocket server"""
        async def handle_connection(websocket):
            client_addr = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}" if websocket.remote_address else "unknown"
            logger.info(f'Connected to client on {client_addr}')
            
            processor = create_websocket_processor(
                websocket=websocket,
                online_asr_proc=self.online_asr,
                min_chunk=self.config.asr_args.min_chunk_size,
                translation_config=self.config.translation_config
            )
            
            try:
                await processor.process_async()
            except Exception as e:
                logger.error(f"Error processing WebSocket connection: {e}")
                await websocket.close(1011, f"Server error: {str(e)}")
            finally:
                logger.info(f'Connection to client {client_addr} closed')
            
        server = WebSocketConnection(self.config.host, self.config.port)
        server.run(handle_connection)
        
    def run_tcp(self):
        """Run TCP server"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.config.host, self.config.port))
            s.listen(1)
            logger.info(f'Listening on {self.config.host}:{self.config.port}')
            
            while True:
                conn, addr = s.accept()
                logger.info(f'Connected to client on {addr}')
                connection = Connection(conn)
                
                proc = self._create_processor(connection)
                proc.process()
                conn.close()
                logger.info('Connection to client closed')
                
    def run(self):
        """Run the server"""
        self.initialize()
        
        if self.config.websocket:
            self.run_websocket()
        else:
            self.run_tcp()

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser()

    # Server options
    parser.add_argument("--host", type=str, default='localhost')
    parser.add_argument("--port", type=int, default=43007)
    parser.add_argument("--websocket", action="store_true",
                        help="Start server in WebSocket mode instead of TCP")
    parser.add_argument("--warmup-file", type=str, dest="warmup_file", 
            help="Path to speech audio wav file for warmup")
    
    # Config file
    parser.add_argument("--config", type=str, default="translation_config.yaml",
                        help="Path to configuration file")
    
    # Translation options
    parser.add_argument("--translate", action="store_true",
                        help="Enable translation of transcript")
    parser.add_argument("--target-language", type=str, 
                        help="Target language for translation (overrides config)")
    parser.add_argument("--translation-interval", type=float, 
                        help="Minimum time between translation API calls (overrides config)")
    parser.add_argument("--max-buffer-time", type=float, 
                        help="Maximum buffer time before translation (overrides config)")
    parser.add_argument("--min-text-length", type=int,
                        help="Minimum text length for translation (overrides config)")
    parser.add_argument("--translation-model", type=str,
                        help="Model to use for translation (overrides config)")
    parser.add_argument("--translation-provider", choices=['gemini', 'openai'],
                        help="Provider to use for translation (overrides config)")
    parser.add_argument("--inactivity-timeout", type=float,
                        help="Inactivity timeout for translation (overrides config)")
    
    # Options from whisper_online
    add_shared_args(parser)
    return parser.parse_args()

def main():
    """Main server function"""
    args = parse_arguments()
    set_logging(args, logger, other="")
    
    # Create server configuration
    config = ServerConfig(args)
    
    # Create and run server
    server = Server(config)
    server.run()

if __name__ == "__main__":
    main()
