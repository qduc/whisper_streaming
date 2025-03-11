#!/usr/bin/env python3
import logging
import time
import json
import asyncio
from typing import Optional, Dict, Any
from server_base import BaseServerProcessor
from translation_utils import TranslationManager
from translation_interfaces import TranslationConfig, TranslationProvider
from translation_processor import AdaptiveTranslationBuffer

logger = logging.getLogger(__name__)

class ConnectionInterface:
    """Interface for connection objects"""
    async def send(self, message: str) -> None:
        raise NotImplementedError

class ServerProcessor(BaseServerProcessor):
    """Standard server processor that handles audio transcription without translation"""
    
    def __init__(self, connection: ConnectionInterface, online_asr_proc: Any, min_chunk: float):
        super().__init__(connection, online_asr_proc, min_chunk)

    async def send_websocket(self, msg: str) -> None:
        """Helper method to send websocket messages asynchronously"""
        # Format message as JSON
        if isinstance(msg, str):
            parts = msg.split(" ", 2)
            if len(parts) >= 3:
                beg, end, text = float(parts[0]), float(parts[1]), parts[2]
                msg = {
                    "type": "transcription",
                    "start": beg,
                    "end": end,
                    "text": text
                }
        
        msg_str = json.dumps(msg) if isinstance(msg, dict) else msg
        await self.connection.send(msg_str)

class TranslatedServerProcessor(BaseServerProcessor):
    """Server processor that adds real-time translation capabilities"""
    
    def __init__(self, 
                 connection: ConnectionInterface,
                 online_asr_proc: Any,
                 min_chunk: float,
                 translation_config: TranslationConfig,
                 translation_manager: Optional[TranslationManager] = None,
                 translation_provider: Optional[TranslationProvider] = None):
        super().__init__(connection, online_asr_proc, min_chunk)
        
        # Initialize translation manager with provided config and optional provider
        self.translation_manager = translation_manager or TranslationManager(
            config=translation_config,
            provider=translation_provider
        )
        
        # Initialize adaptive translation buffer
        self.translation_buffer = AdaptiveTranslationBuffer(
            translation_manager=self.translation_manager,
            min_text_length=translation_config.min_text_length,
            translation_interval=translation_config.interval,
            max_buffer_time=translation_config.max_buffer_time,
            inactivity_timeout=translation_config.inactivity_timeout
        )
        
        # Keep inactivity timeout for reference
        self.inactivity_timeout = translation_config.inactivity_timeout
        
    async def send_websocket(self, msg: Dict[str, Any]) -> None:
        """Helper method to send websocket messages asynchronously"""
        await self.connection.send(json.dumps(msg))
    
    async def send_result(self, o: tuple) -> None:
        """Override to handle translation"""
        if o[0] is not None:
            beg, end = o[0]*1000, o[1]*1000
            if self.last_end is not None:
                beg = max(beg, self.last_end)
            self.last_end = end
            
            # Add text to buffer for later translation
            self.translation_buffer.add_text(o[2], beg, end)

            # Log original text
            text = o[2].replace("  ", " ")
            logger.info(f"ASR {round(o[0], 2)}-{round(o[1], 2)}: {text}")
            
            # Send original transcription
            # await self.send_websocket({
            #     "type": "transcription",
            #     "start": beg,
            #     "end": end,
            #     "text": text
            # })
            
            # Check if we should translate now
            text_to_translate, remainder = self.translation_buffer.get_text_to_translate()
            if text_to_translate:
                await self._process_translation_buffer(text_to_translate)
                # Update the buffer with the remaining text
                if remainder:
                    self.translation_buffer.add_text(remainder, beg, end)
        else:
            logger.debug("No text in this segment")
            
            # Check for leftover text in the buffer that might need translation
            # This replaces the timer-based approach with an event-driven one
            if self.translation_buffer.text_buffer:
                current_time = time.time()
                time_since_last_text = current_time - self.translation_buffer.last_text_time
                
                if time_since_last_text >= self.inactivity_timeout:
                    combined_text = self.translation_buffer.get_combined_text()
                    logger.debug(f"Inactivity timeout exceeded ({time_since_last_text:.1f}s >= {self.inactivity_timeout}s), translating leftover text")
                    await self._process_translation_buffer(combined_text)
            
    async def _process_translation_buffer(self, text) -> None:
        """Process and translate the current buffer contents"""
        start_time, end_time = self.translation_buffer.get_time_bounds()
        
        # Translate the text
        translated_text = await self.translation_manager.translate_text_async(text)

        logger.info(f"TRA {round(start_time/1000, 2)}-{round(end_time/1000, 2)}: {translated_text}")
        
        # Send translation
        await self.send_websocket({
            "type": "translation",
            "start": start_time,
            "end": end_time,
            "original": text,
            "translation": translated_text
        })
        
        # Clear the buffer and update adaptive length
        self.translation_buffer.clear_buffer()
        self.translation_buffer.update_adaptive_min_length()
    
    async def process(self) -> None:
        """Main processing loop with proper cleanup"""
        self.online_asr_proc.init()
        
        # No longer need timer task as we check for leftover text in send_result
        
        try:
            while True:
                # Check for closed WebSocket
                if self.connection.is_closed():
                    logger.info("WebSocket connection closed gracefully")
                    break
                a = self.receive_audio_chunk()
                if a is None:
                    break
                    
                self.online_asr_proc.insert_audio_chunk(a)
                o = self.online_asr_proc.process_iter()
                try:
                    await self.send_result(o)
                except BrokenPipeError:
                    logger.info("broken pipe -- connection closed?")
                    break
                    
            # Process remaining buffer
            if self.translation_buffer.text_buffer:
                try:
                    await self._process_translation_buffer(self.translation_buffer.get_combined_text())
                except BrokenPipeError:
                    logger.info("broken pipe sending final buffer -- connection closed")
                    
        except Exception as e:
            logger.error(f"Error in processor: {e}")
            raise
        finally:
            # No timer task to clean up anymore
            pass
