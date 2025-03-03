#!/usr/bin/env python3
from whisper_online import *
import sys
import argparse
import os
import logging
import socket
from server_base import Connection
from server_processors import ServerProcessor, TranslatedServerProcessor

logger = logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser()

    # Server options
    parser.add_argument("--host", type=str, default='localhost')
    parser.add_argument("--port", type=int, default=43007)
    parser.add_argument("--warmup-file", type=str, dest="warmup_file", 
            help="The path to a speech audio wav file to warm up Whisper so that the very first chunk processing is fast.")
    
    # Translation options
    parser.add_argument("--translate", action="store_true", help="Enable translation of transcript")
    parser.add_argument("--target-language", type=str, default="en", help="Target language for translation")
    parser.add_argument("--translation-interval", type=float, default=3.0, 
                        help="Minimum time in seconds between translation API calls")
    parser.add_argument("--max-buffer-time", type=float, default=10.0, 
                        help="Maximum time to buffer text before forcing translation")
    parser.add_argument("--min-text-length", type=int, default=20,
                        help="Minimum text length to consider for translation")
    parser.add_argument("--translation-model", type=str, default="gemini-2.0-flash",
                        help="Model to use for translation (e.g. gemini-2.0-flash, gpt-4o-mini, gpt-3.5-turbo)")
    parser.add_argument("--translation-provider", choices=['gemini', 'openai'], default='gemini',
                        help="Provider to use for translation (requires appropriate API key)")
    
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

def create_processor(args, connection, online_asr):
    """Create the appropriate processor based on arguments"""
    if args.translate:
        logger.info(f'Translation enabled. Target language: {args.target_language}')
        
        # Create translation processor with configurable parameters
        proc = TranslatedServerProcessor(
            connection, 
            online_asr, 
            args.min_chunk_size, 
            args.target_language,
            model=args.translation_model,
            translation_provider=args.translation_provider
        )
        
        # Set additional translation parameters if provided
        proc.translation_interval = args.translation_interval
        proc.max_buffer_time = args.max_buffer_time
        proc.min_text_length = args.min_text_length
        
        # Log model selection
        if args.translation_provider == 'gemini':
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if gemini_api_key:
                logger.info(f'Using Gemini 2.0 Flash model for translation')
            else:
                logger.warning('GEMINI_API_KEY environment variable not set. Will fall back to OpenAI.')
        else:
            logger.info(f'Using OpenAI model: {args.translation_model}')
        
        logger.info(f'Translation settings: interval={proc.translation_interval}s, '
                    f'max_buffer={proc.max_buffer_time}s, '
                    f'min_length={proc.min_text_length} chars')
    else:
        proc = ServerProcessor(connection, online_asr, args.min_chunk_size)
        
    return proc

def main():
    """Main server function"""
    args = parse_arguments()
    set_logging(args, logger, other="")

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
            proc = create_processor(args, connection, online)
            
            # Process client connection
            proc.process()
            conn.close()
            logger.info('Connection to client closed')
    
    logger.info('Connection closed, terminating.')

if __name__ == "__main__":
    main()
