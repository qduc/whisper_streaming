#!/usr/bin/env python3
import sys
import logging
import time
import json
import asyncio
from server_base import BaseServerProcessor
from translation_utils import TranslationManager

logger = logging.getLogger(__name__)

class TranslationProcessor:
    def __init__(self, translation_manager, min_text_length):
        self.translation_manager = translation_manager
        self.min_text_length = min_text_length
        self.max_text_length = min_text_length * 5  # Don't let buffer exceed 2x the min length
        
    def should_translate(self, combined_text, time_since_last, interval, max_buffer_time):
        """
        Determine if translation should be performed and return the text to translate
        
        Returns:
            str or None: The text to translate, or None if no translation should be performed
        """
        text_length = len(combined_text)
        
        # Buffer timeout
        if time_since_last > max_buffer_time:
            logger.debug(f"Buffer time exceeded ({time_since_last:.1f}s > {max_buffer_time}s), translating")
            return combined_text
        
        # Text too short
        if text_length < self.min_text_length:
            logger.debug(f"Text too short for translation ({text_length} chars < {self.min_text_length}), skipping")
            return None
            
        sentence_part, remainder = self.translation_manager.split_at_sentence_end(combined_text)
        if sentence_part and len(sentence_part) >= self.min_text_length:
            logger.debug("Complete sentence found that meets min length, translating")
            # Return only the complete sentence part
            return sentence_part
                
        # Text above maximum length - translate immediately
        if text_length >= self.max_text_length:
            logger.debug(f"Text too long for buffer ({text_length} chars >= {self.max_text_length}), translating immediately")
            return combined_text
        
        return None

# Updated to use the new async translation method
async def process_translation(connection, text, text_buffer, last_translation_time,
                      target_language='en', model="gemini-2.0-flash", 
                      provider='gemini', interval=4.0, max_buffer_time=5.0,
                      min_text_length=20, inactivity_timeout=2.0, translation_manager=None):
    """
    Process text for translation in the websocket server context
    
    Args:
        connection: The WebSocket connection object
        text: New text to be considered for translation
        text_buffer: List to store accumulated text
        last_translation_time: Last time translation was performed (pass by reference)
        target_language: Target language code for translation
        model: Model to use for translation
        provider: Translation provider ('gemini' or 'openai')
        interval: Minimum time between translation calls
        max_buffer_time: Maximum time to buffer text before forcing translation
        min_text_length: Minimum text length to trigger translation (will be adjusted based on language)
        inactivity_timeout: Seconds of inactivity before translating buffer
        translation_manager: Existing TranslationManager instance to reuse (created if None)
        
    Returns:
        The TranslationManager instance
    """
    # Ensure we have a translation manager
    if translation_manager is None:
        logger.info(f"Creating new TranslationManager with target language {target_language}")
        translation_manager = TranslationManager(
            target_language=target_language,
            model=model,
            translation_provider=provider
        )
    
    processor = TranslationProcessor(translation_manager, min_text_length)
    
    # Add text to buffer and prepare
    text_buffer.append(text)
    current_time = time.time()
    combined_text = " ".join(text_buffer)
    time_since_last = current_time - last_translation_time
    
    # Check if translation is needed and get text to translate
    text_to_translate = processor.should_translate(combined_text, time_since_last, interval, max_buffer_time)
    if text_to_translate:
        # If we're translating a sentence part, keep the remainder in the buffer
        if text_to_translate != combined_text:
            _, remainder = translation_manager.split_at_sentence_end(combined_text)
            text_buffer.clear()
            if remainder:
                text_buffer.append(remainder)
        else:
            text_buffer.clear()
            
        # Perform translation using the returned text
        translated_text = await translation_manager.translate_text_async(text_to_translate)
        
        # Send translation
        try:
            msg = json.dumps({
                "type": "translation",
                "original": text_to_translate,  # Use the actual text that was translated
                "translation": translated_text
            })
            
            if hasattr(connection, 'websocket'):
                await connection.send(msg)
            else:
                connection.send(msg)
                
        except Exception as e:
            logger.error(f"Error sending translation: {e}")
        
        last_translation_time = current_time
    
    return translation_manager

class ServerProcessor(BaseServerProcessor):
    """Standard server processor that handles audio transcription without translation"""
    
    def __init__(self, connection, online_asr_proc, min_chunk):
        super().__init__(connection, online_asr_proc, min_chunk)

    async def send_websocket(self, msg):
        """Helper method to send websocket messages asynchronously"""
        # Format message as JSON
        parts = msg.split(" ")
        if len(parts) > 3:
            beg, end, text = parts[:3], " ".join(parts[3:])
            msg = json.dumps({
                "type": "transcription",
                "start": float(beg),
                "end": float(end),
                "text": text
            })        
        if hasattr(self.connection, 'websocket'):
            await self.connection.send(msg)
        else:
            self.connection.send(msg)

class TranslatedServerProcessor(BaseServerProcessor):
    """Server processor that adds real-time translation capabilities"""
    
    def __init__(self, connection, online_asr_proc, min_chunk, target_language='en',
                 model="gemini-2.0-flash", translation_provider='gemini', 
                 translation_interval=4.0, max_buffer_time=5.0, inactivity_timeout=2.0, 
                 min_text_length=20):
        super().__init__(connection, online_asr_proc, min_chunk)
        
        # Initialize translation manager
        self.translation_manager = TranslationManager(
            target_language=target_language,
            model=model,
            translation_provider=translation_provider
        )
        
        # Translation buffer settings
        self.text_buffer = []
        self.time_buffer = []
        self.last_translation_time = time.time()
        self.last_text_time = time.time()  # Track time of last received text
        self.translation_interval = translation_interval  # Minimum seconds between translation calls
        self.max_buffer_time = max_buffer_time           # Maximum seconds to buffer before forcing translation
        self.inactivity_timeout = inactivity_timeout     # Seconds of inactivity before translating remaining buffer
        self.min_text_length = min_text_length           # Minimum characters to consider translation
        self.adaptive_min_text_length = min_text_length  # Initialize adaptive length same as min length
        self.max_text_length = min_text_length * 5      # Maximum buffer length before forced translation
        
        # Check if connection is WebSocket
        self.is_websocket = hasattr(connection, 'websocket') if connection else False
        
    async def send_websocket(self, msg):
        """Helper method to send websocket messages asynchronously"""
        if hasattr(self.connection, 'websocket'):
            await self.connection.send(msg)
        else:
            self.connection.send(msg)
    
    def update_adaptive_min_length(self):
        """Update adaptive minimum text length after translation"""
        if not hasattr(self.translation_manager, 'translation_history') or not self.translation_manager.translation_history:
            return self.min_text_length
            
        # Calculate the average character ratio from history (max of 10 most recent translations)
        char_ratios = []
        history_items = list(self.translation_manager.translation_history)[-10:]  # Use only recent history
        
        for source, translated in history_items:
            if source and translated:  # Ensure we don't divide by zero
                ratio = len(translated) / len(source)
                char_ratios.append(ratio)
        
        if char_ratios:
            avg_ratio = sum(char_ratios) / len(char_ratios)
            
            # Adjust min_text_length based on the ratio with limits
            # Don't let it go below 25% or above 200% of original value
            if avg_ratio > 0:
                adjusted_length = int(self.min_text_length / avg_ratio)
                # Apply limits to prevent extreme adjustments
                min_adjusted = int(self.min_text_length * 0.25)  # Minimum 25% of original
                max_adjusted = int(self.min_text_length * 2.0)   # Maximum 200% of original
                
                self.adaptive_min_text_length = max(min_adjusted, min(adjusted_length, max_adjusted))
                logger.debug(f"Adjusted min_text_length to {self.adaptive_min_text_length} (original: {self.min_text_length}, ratio: {avg_ratio:.2f})")
                
                # Also update max_text_length based on the new adaptive minimum length
                self.max_text_length = self.adaptive_min_text_length * 5
        
        return self.adaptive_min_text_length
            
    def should_translate_buffer(self):
        """Determine if we should translate the current buffer"""
        current_time = time.time()
        # Check if enough time has passed since last translation
        time_since_last = current_time - self.last_translation_time
        
        # Check for inactivity timeout - translate regardless of length if no new text for a while
        if self.text_buffer and (current_time - self.last_text_time) > self.inactivity_timeout:
            return True

        # Calculate total character length (with spaces for consistency with TranslationProcessor)
        combined_text = " ".join(self.text_buffer)
        text_length = len(combined_text)
        
        # Case 0: Buffer exceeds maximum length - translate immediately
        if text_length >= self.max_text_length:
            logger.debug(f"Text too long for buffer ({text_length} chars >= {self.max_text_length}), translating immediately")
            return True
        
        # Use pre-calculated adaptive min text length
        adaptive_min_text_length = self.adaptive_min_text_length
        
        # Case 1: Buffer has been accumulating for too long
        if self.time_buffer and time_since_last > self.max_buffer_time:
            return True
            
        # Case 2: Enough time has passed AND we have minimum text to translate
        if time_since_last > self.translation_interval and text_length >= adaptive_min_text_length:
            # Check if the buffer ends with a sentence terminator
            if self.translation_manager.is_sentence_end(combined_text):
                return True
            
            # Check if we can at least split at a sentence boundary
            sentence_part, _ = self.translation_manager.split_at_sentence_end(combined_text)
            if sentence_part and len(sentence_part) >= adaptive_min_text_length:
                # We have at least one complete sentence that meets minimum length
                return True
                
        # Don't translate yet
        return False
        
    async def partial_translate_buffer(self):
        """Translate only the complete sentences in the buffer, keeping remainder for next translation"""
        if not self.text_buffer:
            return []
            
        combined_text = " ".join(self.text_buffer)
        sentence_part, remainder = self.translation_manager.split_at_sentence_end(combined_text)
        
        if not sentence_part:  # No complete sentence found
            return []
            
        # Use the async translation method
        translated_text = await self.translation_manager.translate_text_async(sentence_part)
        
        # Calculate appropriate time boundaries
        # A rough approximation based on character proportions 
        if self.time_buffer:
            total_chars = len(combined_text)
            sentence_chars = len(sentence_part)
            char_ratio = sentence_chars / total_chars if total_chars > 0 else 0
            
            start_time = self.time_buffer[0][0]
            end_time_full = self.time_buffer[-1][1]
            
            # Estimate end time proportionally 
            end_time = start_time + (end_time_full - start_time) * char_ratio
            
            # Update time and text buffers to keep remainder
            if remainder:
                # Keep track of remaining text and adjust time buffer
                self.text_buffer = [remainder]
                # Approximate the starting time for remainder
                self.time_buffer = [(end_time, self.time_buffer[-1][1])]
            else:
                # Clear buffers if nothing remains
                self.text_buffer = []
                self.time_buffer = []
                
            self.last_translation_time = time.time()
            
            return [(start_time, end_time, translated_text)]
        
        return []
        
    async def translate_buffer(self):
        """Translate accumulated text buffer and clear it"""
        if not self.text_buffer:
            return []
            
        source_text = " ".join(self.text_buffer)
        # Use the async translation method
        translated_text = await self.translation_manager.translate_text_async(source_text)
        
        # Create list of (begin_time, end_time, text) for each segment
        results = []
        if self.time_buffer:
            results = [(self.time_buffer[0][0], self.time_buffer[-1][1], translated_text)]
            
        # Clear buffers
        self.text_buffer = []
        self.time_buffer = []
        self.last_translation_time = time.time()
        
        return results
        
    async def send_result(self, o):
        """Override to handle translation"""
        if o[0] is not None:
            beg, end = o[0]*1000, o[1]*1000
            if self.last_end is not None:
                beg = max(beg, self.last_end)
            self.last_end = end
            
            # Add text to buffer for later translation
            self.text_buffer.append(o[2])
            self.time_buffer.append((beg, end))
            
            # Update the last text time for inactivity detection
            self.last_text_time = time.time()

            # Log original text and translation status
            text = o[2].replace("  ", " ")  # Replace double spaces with single spaces
            logger.info(f"ASR {round(o[0], 2)}-{round(o[1], 2)}: {text}")
            if self.translation_manager.is_translating:
                logger.info(f"ASR transcript received while translation in progress: {text[:100]}")
            
            # Format message as JSON
            msg = json.dumps({
                "type": "transcription",
                "start": beg,
                "end": end,
                "text": text
            })
            await self.send_websocket(msg)
            
            # Check if we should translate now
            if self.should_translate_buffer():
                # Determine if we should do partial translation or full buffer
                combined_text = " ".join(self.text_buffer)
                has_complete_sentence = self.translation_manager.split_at_sentence_end(combined_text)[0] != ""
                
                if has_complete_sentence and len(combined_text) > self.min_text_length * 2:
                    # Use partial translation when we have long text with complete sentences
                    translated_segments = await self.partial_translate_buffer()
                else:
                    # Otherwise translate the entire buffer
                    translated_segments = await self.translate_buffer()
                
                for t_beg, t_end, translated_text in translated_segments:
                    logger.info(f"Translation {t_beg}-{t_end}: {translated_text}")
                    # Format translation message as JSON for WebSocket or TCP
                    msg = json.dumps({
                        "type": "translation",
                        "start": t_beg,
                        "end": t_end,
                        "original": combined_text,
                        "translation": translated_text
                    })
                    await self.send_websocket(msg)
                self.update_adaptive_min_length()
        else:
            logger.debug("No text in this segment")
            
    async def check_inactivity_timeout(self):
        """Check if we should translate the buffer due to inactivity"""
        if self.text_buffer and (time.time() - self.last_text_time) > self.inactivity_timeout:
            translated_segments = await self.translate_buffer()
            for t_beg, t_end, translated_text in translated_segments:
                logger.info(f"Translation {t_beg}-{t_end} (inactivity timeout): {translated_text}")
                try:
                    # Get the original text
                    combined_text = " ".join(self.text_buffer) if self.text_buffer else ""
                    
                    # Format message as JSON for all clients
                    msg = json.dumps({
                        "type": "translation",
                        "start": t_beg,
                        "end": t_end,
                        "original": combined_text,
                        "translation": translated_text,
                        "reason": "inactivity_timeout"
                    })
                    await self.send_websocket(msg)
                except BrokenPipeError:
                    logger.info("broken pipe sending timeout buffer -- connection closed")
                    break
            self.update_adaptive_min_length()
            return True
        return False
        
    async def process(self):
        """Override to handle final translation buffer and periodic timeout checks"""
        self.online_asr_proc.init()
        try:
            while True:
                # Check if WebSocket connection is still open
                if hasattr(self.connection, 'websocket') and self.connection.websocket.closed:
                    logger.info("WebSocket connection closed gracefully")
                    break

                a = self.receive_audio_chunk()
                
                # Check for inactivity timeout while waiting for audio
                if await self.check_inactivity_timeout() and a is None:
                    # If we've handled timeout and there's no more audio, we can break
                    break
                    
                if a is None:
                    break
                    
                self.online_asr_proc.insert_audio_chunk(a)
                o = self.online_asr_proc.process_iter()
                try:
                    await self.send_result(o)
                except BrokenPipeError:
                    logger.info("broken pipe -- connection closed?")
                    break
                    
            # Process any remaining text in the buffer
            if self.text_buffer:
                translated_segments = await self.translate_buffer()
                for t_beg, t_end, translated_text in translated_segments:
                    logger.info(f"Translation {t_beg}-{t_end} (final buffer): {translated_text}")
                    try:
                        # Get the original text
                        combined_text = " ".join(self.text_buffer) if self.text_buffer else ""
                        
                        # Format message as JSON for all clients
                        msg = json.dumps({
                            "type": "translation",
                            "start": t_beg,
                            "end": t_end,
                            "original": combined_text,
                            "translation": translated_text,
                            "reason": "final_buffer"
                        })
                        await self.send_websocket(msg)
                    except BrokenPipeError:
                        logger.info("broken pipe sending final buffer -- connection closed")
                        break
                self.update_adaptive_min_length()
        except Exception as e:
            logger.error(f"Error in processor: {e}")
            raise
