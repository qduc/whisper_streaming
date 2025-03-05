#!/usr/bin/env python3
import sys
import logging
import time
import json
from server_base import BaseServerProcessor
from translation_utils import TranslationManager

logger = logging.getLogger(__name__)

class ServerProcessor(BaseServerProcessor):
    """Standard server processor that handles audio transcription without translation"""
    
    def __init__(self, connection, online_asr_proc, min_chunk):
        super().__init__(connection, online_asr_proc, min_chunk)

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
        
        # Check if connection is WebSocket
        self.is_websocket = hasattr(connection, 'websocket') if connection else False
        
    def should_translate_buffer(self):
        """Determine if we should translate the current buffer"""
        current_time = time.time()
        # Check if enough time has passed since last translation
        time_since_last = current_time - self.last_translation_time
        
        # Check for inactivity timeout - translate if no new text for a while and buffer not empty
        if self.text_buffer and (current_time - self.last_text_time) > self.inactivity_timeout:
            return True

        # Case 1: Buffer has been accumulating for too long
        if self.time_buffer and time_since_last > self.max_buffer_time:
            return True
            
        # Case 2: Enough time has passed AND we have minimum text to translate
        if time_since_last > self.translation_interval and len("".join(self.text_buffer)) >= self.min_text_length:
            # Check if the buffer ends with a sentence terminator
            combined_text = " ".join(self.text_buffer)
            if self.translation_manager.is_sentence_end(combined_text):
                return True
            
            # Check if we can at least split at a sentence boundary
            sentence_part, _ = self.translation_manager.split_at_sentence_end(combined_text)
            if sentence_part and len(sentence_part) >= self.min_text_length:
                # We have at least one complete sentence that meets minimum length
                return True
            
        # Don't translate yet
        return False
        
    def partial_translate_buffer(self):
        """Translate only the complete sentences in the buffer, keeping remainder for next translation"""
        if not self.text_buffer:
            return []
            
        combined_text = " ".join(self.text_buffer)
        sentence_part, remainder = self.translation_manager.split_at_sentence_end(combined_text)
        
        if not sentence_part:  # No complete sentence found
            return []
            
        # Translate the complete sentence part
        translated_text = self.translation_manager.translate_text(sentence_part)
        
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
        
    def translate_buffer(self):
        """Translate accumulated text buffer and clear it"""
        if not self.text_buffer:
            return []
            
        source_text = " ".join(self.text_buffer)
        translated_text = self.translation_manager.translate_text(source_text)
        
        # Create list of (begin_time, end_time, text) for each segment
        results = []
        if self.time_buffer:
            results = [(self.time_buffer[0][0], self.time_buffer[-1][1], translated_text)]
            
        # Clear buffers
        self.text_buffer = []
        self.time_buffer = []
        self.last_translation_time = time.time()
        
        return results
    
    def send_result(self, o):
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

            # Log original text
            text = o[2].replace("  ", " ")  # Replace double spaces with single spaces
            print(f"{round(o[0], 2)} {round(o[1], 2)} {text}")
            
            # Format for sending to client
            msg = f"{beg} {end} {text}"
            self.connection.send(msg)
            
            # Check if we should translate now
            if self.should_translate_buffer():
                # Determine if we should do partial translation or full buffer
                combined_text = " ".join(self.text_buffer)
                has_complete_sentence = self.translation_manager.split_at_sentence_end(combined_text)[0] != ""
                
                if has_complete_sentence and len(combined_text) > self.min_text_length * 2:
                    # Use partial translation when we have long text with complete sentences
                    translated_segments = self.partial_translate_buffer()
                else:
                    # Otherwise translate the entire buffer
                    translated_segments = self.translate_buffer()
                
                for t_beg, t_end, translated_text in translated_segments:
                    # Format translation message differently for WebSocket vs TCP
                    if hasattr(self.connection, 'websocket'):
                        # For WebSocket, mark the message as containing a translation
                        # The WebSocketClientConnection will parse this format and convert to JSON
                        msg = f"{t_beg} {t_end} {combined_text} (translation) {translated_text}"
                    else:
                        # For TCP, keep the original format
                        msg = f"{t_beg} {t_end} {translated_text}"
                        
                    self.connection.send(msg)
        else:
            logger.debug("No text in this segment")
    
    def check_inactivity_timeout(self):
        """Check if we should translate the buffer due to inactivity"""
        if self.text_buffer and (time.time() - self.last_text_time) > self.inactivity_timeout:
            translated_segments = self.translate_buffer()
            for t_beg, t_end, translated_text in translated_segments:
                print(f"{t_beg} {t_end} {translated_text} (inactivity timeout)", flush=True, file=sys.stderr)
                try:
                    # Get the original text for WebSocket clients
                    combined_text = " ".join(self.text_buffer) if self.text_buffer else ""
                    
                    # Format translation message differently for WebSocket vs TCP
                    if hasattr(self.connection, 'websocket'):
                        # For WebSocket, mark the message as containing a translation
                        msg = f"{t_beg} {t_end} {combined_text} (translation) {translated_text}"
                    else:
                        # For TCP, keep the original format
                        msg = f"{t_beg} {t_end} {translated_text}"
                        
                    self.connection.send(msg)
                except BrokenPipeError:
                    logger.info("broken pipe sending timeout buffer -- connection closed")
                    break
            return True
        return False
            
    def process(self):
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
                if self.check_inactivity_timeout() and a is None:
                    # If we've handled timeout and there's no more audio, we can break
                    break
                    
                if a is None:
                    break
                    
                self.online_asr_proc.insert_audio_chunk(a)
                o = self.online_asr_proc.process_iter()
                try:
                    self.send_result(o)
                except BrokenPipeError:
                    logger.info("broken pipe -- connection closed?")
                    break
                    
            # Process any remaining text in the buffer
            if self.text_buffer:
                translated_segments = self.translate_buffer()
                for t_beg, t_end, translated_text in translated_segments:
                    print(f"{t_beg} {t_end} {translated_text} (final translated buffer)", flush=True, file=sys.stderr)
                    try:
                        # Get the original text for WebSocket clients
                        combined_text = " ".join(self.text_buffer) if self.text_buffer else ""
                        
                        # Format translation message differently for WebSocket vs TCP
                        if hasattr(self.connection, 'websocket'):
                            # For WebSocket, mark the message as containing a translation
                            msg = f"{t_beg} {t_end} {combined_text} (translation) {translated_text}"
                        else:
                            # For TCP, keep the original format
                            msg = f"{t_beg} {t_end} {translated_text}"
                            
                        self.connection.send(msg)
                    except BrokenPipeError:
                        logger.info("broken pipe sending final buffer -- connection closed")
                        break
        except Exception as e:
            logger.error(f"Error in processor: {e}")
            raise
