#!/usr/bin/env python3
import logging
import time
import json
from typing import Optional
from translation_utils import TranslationManager
from translation_providers import TranslationProviderFactory

logger = logging.getLogger(__name__)

class TranslationProcessor:
    def __init__(self, config):
        self.config = config
        self.provider = TranslationProviderFactory.create_provider(config['provider'])
        self.target_language = config['target_language']
        self.model = config['model']
        self.system_prompt = config.get('system_prompt', '')
        self.buffer = []
        self.last_translation_time = 0
        self.last_text_time = 0
        
    def should_translate(self, combined_text, time_since_last, interval, max_buffer_time):
        """
        Determine if translation should be performed and return the text to translate and remainder
        
        Returns:
            tuple: (text_to_translate, remainder) where:
                - text_to_translate (str or None): The text to translate, or None if no translation should be performed
                - remainder (str): Any remaining text that wasn't translated, or empty string if none
        """
        text_length = len(combined_text)
        
        # Buffer timeout
        if time_since_last > max_buffer_time:
            logger.debug(f"Buffer time exceeded ({time_since_last:.1f}s > {max_buffer_time}s), translating")
            return combined_text, ""
        
        # Text too short
        if text_length < self.config['min_text_length']:
            logger.debug(f"Text too short for translation ({text_length} chars < {self.config['min_text_length']}), skipping")
            return None, combined_text
            
        sentence_part, remainder = self.translation_manager.split_at_sentence_end(combined_text)
        if sentence_part and len(sentence_part) >= self.config['min_text_length']:
            return sentence_part, remainder
        
        sentence_part, remainder = self.translation_manager.split_at_comma(combined_text)
        if sentence_part and len(sentence_part) >= self.config['min_text_length']:
            return sentence_part, remainder
                
        # Text above maximum length - translate immediately
        if text_length >= self.config['min_text_length'] * 5:
            logger.debug(f"Text too long ({text_length} chars >= {self.config['min_text_length'] * 5}), translating immediately")
            return combined_text, ""
        
        return None, combined_text

    async def translate_buffer(self) -> Optional[str]:
        """Translate the current buffer if conditions are met"""
        if not self.buffer:
            return None
            
        text = " ".join(self.buffer)
        if len(text) < self.config['min_text_length']:
            return None
            
        try:
            translation = await self.provider.translate_text(
                text, 
                self.target_language, 
                self.model,
                self.system_prompt if self.system_prompt else None
            )
            self.buffer = []
            self.last_translation_time = time.time()
            return translation
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return None

class AdaptiveTranslationBuffer:
    """Manages translation buffer with adaptive minimum length based on translation history"""
    
    def __init__(self, translation_manager, min_text_length=20, translation_interval=4.0, 
                 max_buffer_time=5.0, inactivity_timeout=2.0):
        self.translation_manager = translation_manager
        self.min_text_length = min_text_length
        self.adaptive_min_text_length = min_text_length
        self.max_text_length = min_text_length * 5
        
        self.text_buffer = []
        self.time_buffer = []
        self.last_translation_time = time.time()
        self.last_text_time = time.time()
        
        self.translation_interval = translation_interval
        self.max_buffer_time = max_buffer_time
        self.inactivity_timeout = inactivity_timeout
        
    def update_adaptive_min_length(self):
        """Update adaptive minimum text length based on translation history"""
        if not hasattr(self.translation_manager, 'translation_history') or not self.translation_manager.translation_history:
            return self.min_text_length
            
        char_ratios = []
        history_items = list(self.translation_manager.translation_history)[-10:]
        
        for source, translated in history_items:
            if source and translated:
                ratio = len(translated) / len(source)
                char_ratios.append(ratio)
        
        if char_ratios:
            avg_ratio = sum(char_ratios) / len(char_ratios)
            
            if avg_ratio > 0:
                adjusted_length = int(self.min_text_length / avg_ratio)
                min_adjusted = int(self.min_text_length * 0.25)
                max_adjusted = int(self.min_text_length * 2.0)
                
                self.adaptive_min_text_length = max(min_adjusted, min(adjusted_length, max_adjusted))
                logger.debug(f"Adjusted min_text_length to {self.adaptive_min_text_length} (original: {self.min_text_length}, ratio: {avg_ratio:.2f})")
                
                self.max_text_length = self.adaptive_min_text_length * 5
        
        return self.adaptive_min_text_length

    def add_text(self, text, start_time, end_time):
        """Add text to buffer with timing information"""
        self.text_buffer.append(text)
        self.time_buffer.append((start_time, end_time))
        self.last_text_time = time.time()
        
    def clear_buffer(self):
        """Clear both text and time buffers"""
        self.text_buffer.clear()
        self.time_buffer.clear()
        self.last_translation_time = time.time()
        
    def get_combined_text(self):
        """Get combined text from buffer"""
        return " ".join(self.text_buffer)
        
    def get_time_bounds(self):
        """Get start and end time of current buffer"""
        if not self.time_buffer:
            return None, None
        return self.time_buffer[0][0], self.time_buffer[-1][1]
        
    def should_translate(self):
        """Determine if we should translate the current buffer"""
        if not self.text_buffer:
            return False
            
        current_time = time.time()
        time_since_last = current_time - self.last_translation_time
        
        # Check for inactivity timeout
        if (current_time - self.last_text_time) > self.inactivity_timeout:
            return True

        combined_text = self.get_combined_text()
        text_length = len(combined_text)
        
        # Buffer exceeds maximum length
        if text_length >= self.max_text_length:
            return True
        
        # Buffer has been accumulating for too long
        if time_since_last > self.max_buffer_time:
            return True
            
        # Enough time has passed and we have minimum text
        if time_since_last > self.translation_interval and text_length >= self.adaptive_min_text_length:
            if self.translation_manager.is_sentence_end(combined_text):
                return True
                
            sentence_part, _ = self.translation_manager.split_at_sentence_end(combined_text)
            if sentence_part and len(sentence_part) >= self.adaptive_min_text_length:
                return True
                
        return False

async def process_translation(connection, text, text_buffer, last_translation_time,
                      target_language='en', model="gemini-2.0-flash", 
                      provider='gemini', interval=4.0, max_buffer_time=5.0,
                      min_text_length=20, inactivity_timeout=2.0, translation_manager=None):
    """Process text for translation in the websocket server context"""
    if translation_manager is None:
        logger.info(f"Creating new TranslationManager with target language {target_language}")
        translation_manager = TranslationManager(
            target_language=target_language,
            model=model,
            translation_provider=provider
        )
    
    processor = TranslationProcessor(translation_manager, min_text_length)
    
    text_buffer.append(text)
    current_time = time.time()
    combined_text = " ".join(text_buffer)
    time_since_last = current_time - last_translation_time
    
    text_to_translate, remainder = processor.should_translate(combined_text, time_since_last, interval, max_buffer_time)
    if text_to_translate:
        text_buffer.clear()
        text_buffer.append(remainder)
            
        translated_text = await translation_manager.translate_text_async(text_to_translate)
        
        try:
            msg = json.dumps({
                "type": "translation",
                "original": text_to_translate,
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