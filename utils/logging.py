#!/usr/bin/env python3
import logging

def setup_logging(args, logger, other="_server"):
    """Configure logging for all components of the whisper streaming system.
    
    Args:
        args: ArgumentParser args containing log_level
        logger: Logger instance to configure
        other (str): Suffix for whisper_online logger, defaults to "_server"
    """
    logging.basicConfig(format='%(levelname)s\t%(message)s')
    
    # Core components
    logger.setLevel(args.log_level)
    logging.getLogger("whisper_online"+other).setLevel(args.log_level)
    
    # Server components
    logging.getLogger("server_processors").setLevel(args.log_level)
    logging.getLogger("server_base").setLevel(args.log_level)
    logging.getLogger("websocket_connection").setLevel(args.log_level)
    
    # Translation components
    logging.getLogger("translation_utils").setLevel(args.log_level)
    logging.getLogger("translation_processor").setLevel(args.log_level)
    logging.getLogger("translation_providers").setLevel(args.log_level)
    
    # VAD components 
    logging.getLogger("silero_vad_iterator").setLevel(args.log_level)