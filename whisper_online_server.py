#!/usr/bin/env python3
from whisper_online import *
import sys
import argparse
import os
import logging
import socket
import yaml
from server_base import Connection
from server_processors import ServerProcessor, TranslatedServerProcessor

logger = logging.getLogger(__name__)

def load_config(config_path):
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

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser()

    # Server options
    parser.add_argument("--host", type=str, default='localhost')
    parser.add_argument("--port", type=int, default=43007)
    parser.add_argument("--warmup-file", type=str, dest="warmup_file", 
            help="The path to a speech audio wav file to warm up Whisper so that the very first chunk processing is fast.")
    
    # Config file
    parser.add_argument("--config", type=str, default="translation_config.yaml",
                        help="Path to configuration file")
    
    # Translation options
    parser.add_argument("--translate", action="store_true", help="Enable translation of transcript")
    parser.add_argument("--target-language", type=str, 
                        help="Target language for translation (overrides config)")
    parser.add_argument("--translation-interval", type=float, 
                        help="Minimum time in seconds between translation API calls (overrides config)")
    parser.add_argument("--max-buffer-time", type=float, 
                        help="Maximum time to buffer text before forcing translation (overrides config)")
    parser.add_argument("--min-text-length", type=int,
                        help="Minimum text length to consider for translation (overrides config)")
    parser.add_argument("--translation-model", type=str,
                        help="Model to use for translation (overrides config)")
    parser.add_argument("--translation-provider", choices=['gemini', 'openai'],
                        help="Provider to use for translation (overrides config)")
    parser.add_argument("--inactivity-timeout", type=float,
                        help="Seconds of inactivity before translating remaining buffer (overrides config)")
    
    # Options from whisper_online
    add_shared_args(parser)
    return parser.parse_args()

def warmup_asr(args, asr):
    """Warm up the ASR model to reduce initial processing time"""
    msg = "Whisper is not warmed up. The first chunk processing may take longer."
    if args.warmup_file:
        if os.path.isfile(args.warmup_file):
            a = load_audio_chunk(args.warmup_file, 0, 1)
            asr.transcribe(a)
            logger.info("Whisper is warmed up.")
        else:
            logger.critical("The warm up file is not available. " + msg)
            sys.exit(1)
    else:
        logger.warning(msg)

def get_translation_settings(args, config):
    """Get translation settings with command line arguments overriding config values"""
    # Get configuration from file
    translation_config = config.get('translation', {})
    
    # Create settings dict with defaults from config
    settings = {
        'target_language': translation_config.get('target_language', 'en'),
        'model': translation_config.get('model', 'gemini-2.0-flash'),
        'provider': translation_config.get('provider', 'gemini'),
        'interval': translation_config.get('interval', 3.0),
        'max_buffer_time': translation_config.get('max_buffer_time', 10.0),
        'min_text_length': translation_config.get('min_text_length', 20),
        'inactivity_timeout': translation_config.get('inactivity_timeout', 2.0)
    }
    
    # Override with command line arguments if provided
    if args.target_language is not None:
        settings['target_language'] = args.target_language
    if args.translation_model is not None:
        settings['model'] = args.translation_model
    if args.translation_provider is not None:
        settings['provider'] = args.translation_provider
    if args.translation_interval is not None:
        settings['interval'] = args.translation_interval
    if args.max_buffer_time is not None:
        settings['max_buffer_time'] = args.max_buffer_time
    if args.min_text_length is not None:
        settings['min_text_length'] = args.min_text_length
    if args.inactivity_timeout is not None:
        settings['inactivity_timeout'] = args.inactivity_timeout
        
    return settings

def create_processor(args, connection, online_asr, config):
    """Create the appropriate processor based on arguments and config"""
    if args.translate:
        # Get settings with command line overrides
        settings = get_translation_settings(args, config)
        
        logger.info(f'Translation enabled. Target language: {settings["target_language"]}')
        
        # Create translation processor with all parameters
        proc = TranslatedServerProcessor(
            connection, 
            online_asr, 
            args.min_chunk_size, 
            target_language=settings['target_language'],
            model=settings['model'],
            translation_provider=settings['provider'],
            translation_interval=settings['interval'],
            max_buffer_time=settings['max_buffer_time'],
            min_text_length=settings['min_text_length'],
            inactivity_timeout=settings['inactivity_timeout']
        )
        
        # Log model selection and provider
        if settings['provider'] == 'gemini':
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if gemini_api_key:
                logger.info(f'Using Gemini model: {settings["model"]} for translation')
            else:
                logger.warning('GEMINI_API_KEY environment variable not set. Will fall back to OpenAI.')
        else:
            logger.info(f'Using OpenAI model: {settings["model"]}')
        
        # Log translation settings
        logger.info(f'Translation settings: interval={proc.translation_interval}s, '
                    f'max_buffer={proc.max_buffer_time}s, '
                    f'min_length={proc.min_text_length} chars, '
                    f'inactivity_timeout={proc.inactivity_timeout}s')
    else:
        proc = ServerProcessor(connection, online_asr, args.min_chunk_size)
        
    return proc

def main():
    """Main server function"""
    args = parse_arguments()
    set_logging(args, logger, other="")
    
    # Load configuration
    config = load_config(args.config)

    # Initialize ASR model
    asr, online = asr_factory(args)
    warmup_asr(args, asr)

    # Start server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Set SO_REUSEADDR option to avoid "Address already in use" error
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((args.host, args.port))
        s.listen(1)
        logger.info('Listening on ' + str((args.host, args.port)))
        
        while True:
            conn, addr = s.accept()
            logger.info('Connected to client on {}'.format(addr))
            connection = Connection(conn)
            
            # Create appropriate processor
            proc = create_processor(args, connection, online, config)
            
            # Process client connection
            proc.process()
            conn.close()
            logger.info('Connection to client closed')
    
    logger.info('Connection closed, terminating.')

if __name__ == "__main__":
    main()
