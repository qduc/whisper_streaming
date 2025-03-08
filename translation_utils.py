#!/usr/bin/env python3
import logging
import openai
import os
import asyncio
import yaml
from collections import deque

logger = logging.getLogger(__name__)

class TranslationManager:
    """Handles translation of text using various API providers"""
    
    def __init__(self, target_language='en', model="gemini-2.0-flash", translation_provider='gemini',
                 history_size=4, max_history_tokens=200, use_history=True, config_path="translation_config.yaml"):
        self.target_language = target_language
        self.model = model
        self.translation_provider = translation_provider
        self.config_path = config_path
        
        # Default system prompt
        self.default_system_prompt = f"Translate the following speech transcription into {self.target_language} in a natural, fluent way, ensuring clarity and readability. Maintain the original meaning while using wording that sounds natural to a native Vietnamese speaker. Avoid overly literal translations and focus on conveying the message naturally. Output only the translated text without any additional commentary or formatting."
        
        # Load system prompt from config if available
        self.system_prompt = self._load_system_prompt()
        
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
        
        # Queue system for translation requests
        self._translation_queue = asyncio.Queue()
        self._translation_lock = asyncio.Lock()
        self._translation_in_progress = False
        self._translation_task = None

        # Initialize NLTK
        try:
            import nltk
            from nltk.tokenize import sent_tokenize
            nltk.download('punkt')
            nltk.download('punkt_tab')
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
                # Get the next text to translate from the queue
                text = await self._translation_queue.get()
                self._translation_in_progress = True

                try:
                    result = await self._perform_translation(text)
                    # Cache the result
                    if len(self.translation_cache) >= self.cache_size_limit:
                        oldest = self.cache_queue.popleft()
                        if oldest in self.translation_cache:
                            del self.translation_cache[oldest]
                    
                    self.translation_cache[text] = result
                    self.cache_queue.append(text)
                    self.translation_history.append((text, result))
                    
                finally:
                    self._translation_in_progress = False
                    self._translation_queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in translation worker: {e}")

    async def translate_text_async(self, text):
        """Async version of translate_text that uses the queue system"""
        # Check cache first for immediate result
        if text in self.translation_cache:
            logger.debug(f"Translation cache hit: {text[:30]}...")
            return self.translation_cache[text]
        
        # Ensure worker is running
        await self.start_translation_worker()
        
        # Add to queue and wait for result
        await self._translation_queue.put(text)
        
        # Wait for this item to be processed
        await self._translation_queue.join()
        
        # Return the cached result
        return self.translation_cache.get(text, text)

    async def _perform_translation(self, text):
        """Internal method to perform the actual translation API call"""
        try:
            messages = self._prepare_messages_with_history(text)
            
            if self.translation_provider == 'gemini':
                gemini_api_key = os.environ.get("GEMINI_API_KEY")
                if not gemini_api_key:
                    logger.warning("GEMINI_API_KEY environment variable not set. Falling back to OpenAI.")
                    client = openai.AsyncOpenAI()  # Use async client
                else:
                    client = openai.AsyncOpenAI(  # Use async client
                        api_key=gemini_api_key,
                        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                    )
                
                # Use native async call instead of asyncio.to_thread
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=1000
                )
            elif self.translation_provider == 'openai':
                client = openai.AsyncOpenAI()  # Use async client
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=1000
                )
            else:
                raise ValueError(f"Unknown translation provider: {self.translation_provider}")
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text  # Fall back to original text on error
    
    def _load_system_prompt(self):
        """Load system prompt from config file or use the default one if not available"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as file:
                    config = yaml.safe_load(file)
                    
                if config and 'translation' in config and 'system_prompt' in config['translation']:
                    custom_prompt = config['translation']['system_prompt']
                    if custom_prompt and custom_prompt.strip():
                        logger.debug("Using custom system prompt from config")
                        return custom_prompt.replace('{target_language}', self.target_language)
        except Exception as e:
            logger.error(f"Error loading system prompt from config: {e}")
            
        logger.debug("Using default system prompt")
        return self.default_system_prompt
        
    def is_sentence_end(self, text):
        """Check if text likely ends with a sentence terminator"""
        if not text:
            return False
        return any(text.rstrip().endswith(marker) for marker in self.sentence_end_markers)
    
    def _prepare_messages_with_history(self, text):
        """Prepare messages array with history as user/assistant pairs"""
        # Start with system message
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # Add history as user/assistant pairs if enabled
        if self.use_history and self.translation_history:
            # print(f"History enabled. Current history size: {len(self.translation_history)}")
            total_chars = 0
            history_pairs = []
            
            # Process history from oldest to newest to maintain conversation flow
            history_list = list(self.translation_history)
            # print(f"Processing {len(history_list)} history items")
            
            for idx, (source, target) in enumerate(history_list):
                # Rough estimation of token count
                pair_chars = len(source) + len(target)
                # print(f"History item {idx}: source chars: {len(source)}, target chars: {len(target)}, total: {pair_chars}")
                
                if total_chars + pair_chars > self.max_history_tokens * 4:
                    # print(f"History limit reached at item {idx}. Current chars: {total_chars}, limit: {self.max_history_tokens * 4}")
                    break
                    
                # Add this pair to our history
                history_pairs.append((source, target))
                total_chars += pair_chars
                # print(f"Added to history. Running total: {total_chars} chars")
            
            # print(f"Final history pairs to include: {len(history_pairs)}")
            # Add the history pairs to messages
            for source, target in history_pairs:
                messages.append({"role": "user", "content": source})
                messages.append({"role": "assistant", "content": target})
        # else:
        #     print(f"History disabled or empty. use_history: {self.use_history}, history size: {len(self.translation_history) if self.translation_history else 0}")
        
        # Add the current text to translate
        messages.append({"role": "user", "content": text})
        # print(f"Final message count: {len(messages)}")
        # print(f"Prepared messages: {messages}")
        return messages
    
    def translate_text(self, text):
        """Translate text with caching to reduce API calls (synchronous version)"""
        # This is kept for backward compatibility
        # For new code, prefer using translate_text_async
        
        # Check cache first
        if text in self.translation_cache:
            logger.debug(f"Translation cache hit: {text[:30]}...")
            return self.translation_cache[text]
        
        # Make API call if not in cache
        try:
            # Prepare messages with history
            messages = self._prepare_messages_with_history(text)
            result = self._perform_translation_sync(messages, text)
            return result
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text  # Fall back to original text on error
    
    def _perform_translation_sync(self, messages, text):
        """Internal synchronous method to perform translation API call (for backward compatibility)"""
        if self.translation_provider == 'gemini':
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if not gemini_api_key:
                logger.warning("GEMINI_API_KEY environment variable not set. Falling back to OpenAI.")
                client = openai.OpenAI()
            else:
                client = openai.OpenAI(
                    api_key=gemini_api_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                )
                
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1000
            )
        elif self.translation_provider == 'openai':
            # Use standard OpenAI model
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1000
            )
        else:
            raise ValueError(f"Unknown translation provider: {self.translation_provider}")
            
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
        
    def split_at_sentence_end(self, text):
        """Split text at the last sentence end using NLTK."""
        if not text:
            return "", ""
        
        if self.sent_tokenize is None:
            return self._manual_split_at_sentence_end(text)
        
        # Get sentences using NLTK
        sentences = self.sent_tokenize(text)
        
        if len(sentences) == 0:
            return "", text.strip()
        
        # Check if the last sentence ends with a sentence marker
        last_sentence = sentences[-1].strip()
        has_end_marker = any(last_sentence.endswith(marker) for marker in self.sentence_end_markers)
            
        if len(sentences) == 1:
            if has_end_marker:
                return last_sentence, ""
            return "", text.strip()
        
        if not has_end_marker:
            # Join all complete sentences
            complete_part = ' '.join(sentences[:-1]).strip()
            return complete_part, last_sentence
        
        # All sentences are complete
        return ' '.join(sentences).strip(), ""

    def _manual_split_at_sentence_end(self, text):
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
    def is_translating(self):
        """Check if translation is in progress"""
        return self._translation_in_progress
