import sys
import logging
import openai
import time
import os
from collections import deque

logger = logging.getLogger(__name__)

class TranslatedServerProcessor:
    def __init__(self, c, online_asr_proc, min_chunk, target_language='en', 
                 history_size=5, max_history_tokens=500, use_history=True,
                 model="gemini-2.0-flash", use_gemini=True):
        # No import of ServerProcessor
        self.connection = c
        self.online_asr_proc = online_asr_proc
        self.min_chunk = min_chunk
        self.last_end = None
        self.is_first = True
        self.target_language = target_language
        self.model = model
        self.use_gemini = use_gemini
        
        # Initialize for audio processing
        self.SAMPLING_RATE = 16000
        
        # Translation buffer settings
        self.text_buffer = []
        self.time_buffer = []
        self.last_translation_time = time.time()
        self.translation_interval = 4.0  # Minimum seconds between translation calls
        self.max_buffer_time = 5.0     # Maximum seconds to buffer before forcing translation
        self.min_text_length = 20       # Minimum characters to consider translation
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

    def should_translate_buffer(self):
        """Determine if we should translate the current buffer"""
        if not self.text_buffer:
            return False
            
        current_time = time.time()
        buffer_text = " ".join(self.text_buffer)
        
        # Split at last sentence end if possible and text is long enough
        sentence_part, remainder = self.split_at_sentence_end(buffer_text)
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
        translated_text = self.translate_text(source_text)
        
        # Create list of (begin_time, end_time, text) for each segment
        results = []
        if self.time_buffer:
            results = [(self.time_buffer[0][0], self.time_buffer[-1][1], translated_text)]
            
        # Clear buffers
        self.text_buffer = []
        self.time_buffer = []
        self.last_translation_time = time.time()
        
        return results

    def receive_audio_chunk(self):
        # Implement the method directly, duplicating the ServerProcessor logic
        import io
        import soundfile
        import librosa
        import numpy as np
        
        # receive all audio that is available by this time
        # blocks operation if less than self.min_chunk seconds is available
        # unblocks if connection is closed or a chunk is available
        out = []
        minlimit = self.min_chunk * self.SAMPLING_RATE
        while sum(len(x) for x in out) < minlimit:
            raw_bytes = self.connection.non_blocking_receive_audio()
            if not raw_bytes:
                break
            sf = soundfile.SoundFile(io.BytesIO(raw_bytes), channels=1, endian="LITTLE", 
                                    samplerate=self.SAMPLING_RATE, subtype="PCM_16", format="RAW")
            audio, _ = librosa.load(sf, sr=self.SAMPLING_RATE, dtype=np.float32)
            out.append(audio)
        if not out:
            return None
        conc = np.concatenate(out)
        if self.is_first and len(conc) < minlimit:
            return None
        self.is_first = False
        return np.concatenate(out)
    
    def send_result(self, o):
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
        self.online_asr_proc.init()
        try:
            while True:
                a = self.receive_audio_chunk()
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
                        msg = f"{t_beg} {t_end} {translated_text}"
                        self.connection.send(msg)
                    except BrokenPipeError:
                        logger.info("broken pipe sending final buffer -- connection closed")
                        break
        except Exception as e:
            logger.error(f"Error in translation processor: {e}")
            raise
