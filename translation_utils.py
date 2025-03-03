#!/usr/bin/env python3
import logging
import openai
import os
from collections import deque

logger = logging.getLogger(__name__)

class TranslationManager:
    """Handles translation of text using various API providers"""
    
    def __init__(self, target_language='en', model="gemini-2.0-flash", use_gemini=True,
                 history_size=5, max_history_tokens=500, use_history=True):
        self.target_language = target_language
        self.model = model
        self.use_gemini = use_gemini
        
        # Translation cache settings
        self.translation_cache = {}     # Simple cache for translations
        self.cache_size_limit = 100     # Maximum cache entries
        self.cache_queue = deque()      # For maintaining cache order
        
        # Translation history settings
        self.use_history = use_history                    # Whether to use history for context
        self.translation_history = deque(maxlen=history_size)  # How many past translations to keep
        self.max_history_tokens = max_history_tokens      # Approximate max tokens to use from history
        
        # Punctuation that likely indicates a sentence end
        self.sentence_end_markers = ['.', '!', '?', '。', '！', '？', '।', '॥', '։', '؟']
        
    def is_sentence_end(self, text):
        """Check if text likely ends with a sentence terminator"""
        if not text:
            return False
        return any(text.rstrip().endswith(marker) for marker in self.sentence_end_markers)
    
    def _prepare_messages_with_history(self, text):
        """Prepare messages array with history as user/assistant pairs"""
        # Start with system message
        messages = [
            {"role": "system", "content": f"Translate the following speech transcript to {self.target_language}. Output only the translated text without any explanations."}
        ]
        
        # Add history as user/assistant pairs if enabled
        if self.use_history and self.translation_history:
            total_chars = 0
            history_pairs = []
            
            # Process history starting from most recent (to prioritize recent context if we hit token limit)
            for source, target in reversed(self.translation_history):
                # Rough estimation of token count
                pair_chars = len(source) + len(target)
                if total_chars + pair_chars > self.max_history_tokens * 4:
                    break
                    
                # Add this pair to our history (in reverse order since we're going backward)
                history_pairs.insert(0, (source, target))
                total_chars += pair_chars
            
            # Add the history pairs to messages
            for source, target in history_pairs:
                messages.append({"role": "user", "content": source})
                messages.append({"role": "assistant", "content": target})
        
        # Add the current text to translate
        messages.append({"role": "user", "content": text})
        
        return messages
        
    def translate_text(self, text):
        """Translate text with caching to reduce API calls"""
        # Check cache first
        if text in self.translation_cache:
            logger.debug(f"Translation cache hit: {text[:30]}...")
            return self.translation_cache[text]
        
        # Make API call if not in cache
        try:
            # Prepare messages with history
            messages = self._prepare_messages_with_history(text)
            
            if self.use_gemini:
                # Use Gemini 2.0 Flash model
                gemini_api_key = os.environ.get("GEMINI_API_KEY")
                if not gemini_api_key:
                    logger.warning("GEMINI_API_KEY environment variable not set. Falling back to OpenAI.")
                    client = openai.OpenAI()
                else:
                    client = openai.OpenAI(
                        api_key=gemini_api_key,
                        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                    )
                    logger.debug("Using Gemini API for translation")
                    
                response = client.chat.completions.create(
                    model="gemini-2.0-flash",  # Use Gemini's model
                    messages=messages,
                    max_tokens=1000
                )
            else:
                # Use standard OpenAI model
                client = openai.OpenAI()
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=1000
                )
                
            translated = response.choices[0].message.content.strip()
            
            # Add to cache
            if len(self.translation_cache) >= self.cache_size_limit:
                # Remove oldest entry
                oldest = self.cache_queue.popleft()
                if oldest in self.translation_cache:
                    del self.translation_cache[oldest]
            
            # Add to translation history
            self.translation_history.append((text, translated))
            
            self.translation_cache[text] = translated
            self.cache_queue.append(text)
            
            return translated
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text  # Fall back to original text on error
            
    def split_at_sentence_end(self, text):
        """Split text at the last sentence end marker, returns (sentence_part, remainder)"""
        if not text:
            return "", ""
            
        # Find the last occurrence of any sentence end marker
        last_end_pos = -1
        for marker in self.sentence_end_markers:
            pos = text.rfind(marker)
            if pos > last_end_pos:
                last_end_pos = pos
                
        if last_end_pos >= 0:
            # Include the marker in the first part
            return text[:last_end_pos + 1].strip(), text[last_end_pos + 1:].strip()
        return "", text.strip()
