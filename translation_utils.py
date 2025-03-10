#!/usr/bin/env python3
import logging
import os
import asyncio
import yaml
from collections import deque
from typing import Optional, List, Tuple, Dict
from translation_interfaces import TranslationProvider, TranslationConfig
from translation_providers import TranslationProviderFactory

logger = logging.getLogger(__name__)

class TranslationManager:
    """Handles translation of text using various API providers"""
    
    def __init__(self, 
                 config: TranslationConfig,
                 provider: Optional[TranslationProvider] = None,
                 max_history_tokens: int = 200):
        self.config = config
        self.provider = provider or TranslationProviderFactory.create_provider(config.provider)
        
        # Translation cache settings
        self.translation_cache = {}
        self.cache_size_limit = 100
        self.cache_queue = deque()
        
        # Translation history settings
        self.translation_history = deque(maxlen=config.history_size)
        self.max_history_tokens = max_history_tokens
        
        # Punctuation that likely indicates a sentence end
        self.sentence_end_markers = ['.', '!', '?', '。', '！', '？', '।', '॥', '։', '؟']
        
        # Queue system for translation requests
        self._translation_queue = asyncio.Queue()
        self._translation_lock = asyncio.Lock()
        self._translation_in_progress = False
        self._translation_task = None
        
        logger.info(f"Translation history enabled with size: {config.history_size}")
        
        # Initialize NLTK
        try:
            import nltk
            from nltk.tokenize import sent_tokenize
            nltk.download('punkt', quiet=True)
            self.sent_tokenize = sent_tokenize
            logger.debug("NLTK sentence tokenizer loaded")
        except ImportError:
            logger.warning("NLTK not available, will use manual sentence splitting")
            self.sent_tokenize = None

    async def start_translation_worker(self):
        """Start the background translation worker"""
        if self._translation_task is None:
            self._translation_task = asyncio.create_task(self._translation_worker())
            logger.debug("Started translation worker task")

    async def _translation_worker(self):
        """Background worker that processes translation requests"""
        while True:
            try:
                text = await self._translation_queue.get()
                self._translation_in_progress = True

                try:
                    # Get recent history items as context for the translation
                    history_items = list(self.translation_history)
                    
                    # Pass history to translation provider if available
                    result = await self.provider.translate_text(
                        text=text,
                        target_language=self.config.target_language,
                        model=self.config.model,
                        system_prompt=self.config.system_prompt,
                        history=history_items if history_items else None
                    )
                    
                    # Cache the result
                    if len(self.translation_cache) >= self.cache_size_limit:
                        oldest = self.cache_queue.popleft()
                        if oldest in self.translation_cache:
                            del self.translation_cache[oldest]
                    
                    self.translation_cache[text] = result
                    self.cache_queue.append(text)
                    self.translation_history.append((text, result))
                    
                    logger.debug(f"Translation completed with history size: {len(history_items)}")
                    
                finally:
                    self._translation_in_progress = False
                    self._translation_queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in translation worker: {e}")

    async def translate_text_async(self, text: str) -> str:
        """Async version of translate_text that uses the queue system"""
        if text in self.translation_cache:
            logger.debug(f"Translation cache hit: {text[:30]}...")
            return self.translation_cache[text]
        
        await self.start_translation_worker()
        await self._translation_queue.put(text)
        await self._translation_queue.join()
        
        return self.translation_cache.get(text, text)
        
    def is_sentence_end(self, text: str) -> bool:
        """Check if text likely ends with a sentence terminator"""
        if not text:
            return False
        return any(text.rstrip().endswith(marker) for marker in self.sentence_end_markers)
    
    def split_at_sentence_end(self, text: str) -> Tuple[str, str]:
        """Split text at the last sentence end"""
        if not text:
            return "", ""
        
        if self.sent_tokenize is None:
            return self._manual_split_at_sentence_end(text)
        
        sentences = self.sent_tokenize(text)
        
        if len(sentences) == 0:
            return "", text.strip()
        
        last_sentence = sentences[-1].strip()
        has_end_marker = any(last_sentence.endswith(marker) for marker in self.sentence_end_markers)
            
        if len(sentences) == 1:
            if has_end_marker:
                return last_sentence, ""
            return "", text.strip()
        
        if not has_end_marker:
            complete_part = ' '.join(sentences[:-1]).strip()
            return complete_part, last_sentence
        
        return ' '.join(sentences).strip(), ""
    
    def split_at_comma(self, text: str) -> Tuple[str, str]:
        """Split text at the last comma"""
        if not text:
            return "", ""
        
        last_comma = text.rfind(',')
        if last_comma == -1:
            return "", text.strip()
        
        return text[:last_comma].strip(), text[last_comma + 1:].strip()

    def _manual_split_at_sentence_end(self, text: str) -> Tuple[str, str]:
        """Manual split at sentence end if NLTK is not available"""
        last_end = -1
        for marker in self.sentence_end_markers:
            pos = text.rfind(marker)
            if pos > last_end:
                last_end = pos
        
        if last_end == -1:
            return "", text.strip()
            
        return text[:last_end + 1].strip(), text[last_end + 1:].strip()
    
    @property
    def is_translating(self) -> bool:
        """Check if translation is in progress"""
        return self._translation_in_progress
