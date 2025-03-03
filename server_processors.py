#!/usr/bin/env python3
import sys
import logging
import time
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
                 model="gemini-2.0-flash", translation_provider='gemini'):
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
        self.translation_interval = 4.0  # Minimum seconds between translation calls
        self.max_buffer_time = 5.0       # Maximum seconds to buffer before forcing translation
        self.min_text_length = 20        # Minimum characters to consider translation
        
    def should_translate_buffer(self):
        """Determine if we should translate the current buffer"""
        if not self.text_buffer:
            return False
            
        current_time = time.time()
        buffer_text = " ".join(self.text_buffer)
        
        # Split at last sentence end if possible and text is long enough
        sentence_part, remainder = self.translation_manager.split_at_sentence_end(buffer_text)
        if sentence_part and len(sentence_part) >= self.min_text_length:
            # Keep remainder in buffer
            if remainder:
                self.text_buffer = [remainder]
            else:
                self.text_buffer = []
            return True
            
        # Second priority: Force translation if buffer is too old
        if current_time - self.last_translation_time > self.max_buffer_time and self.text_buffer:
            return True
            
        # Third priority: Very long text regardless of sentence completion
        if len(buffer_text) > 150:
            return True
            
        # Last priority: Minimum length + time interval
        if len(buffer_text) >= self.min_text_length and \
           current_time - self.last_translation_time > self.translation_interval:
            # Only translate if we have at least a comma or similar pause
            return any(marker in buffer_text for marker in [',', '、', ';', '：', ':', '-'])
            
        return False
        
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

            # Log original text
            text = o[2].replace("  ", " ")  # Replace double spaces with single spaces
            print(f"{round(o[0], 2)} {round(o[1], 2)} {text}")
            
            # Check if we should translate now
            if self.should_translate_buffer():
                translated_segments = self.translate_buffer()
                
                for t_beg, t_end, translated_text in translated_segments:
                    msg = f"{t_beg} {t_end} {translated_text}"
                    self.connection.send(msg)
        else:
            logger.debug("No text in this segment")
            
    def process(self):
        """Override to handle final translation buffer"""
        super().process()
        
        # Process any remaining text in the buffer
        if self.text_buffer:
            translated_segments = self.translate_buffer()
            for t_beg, t_end, translated_text in translated_segments:
                print(f"{t_beg} {t_end} {translated_text} (final translated buffer)", flush=True, file=sys.stderr)
                try:
                    msg = f"{t_beg} {t_end} {translated_text}"
                    self.connection.send(msg)
                except BrokenPipeError:
                    logger.info("broken pipe sending final buffer -- connection closed")
                    break
