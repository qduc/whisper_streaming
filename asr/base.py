#!/usr/bin/env python3
import sys
import logging

logger = logging.getLogger(__name__)

class ASRBase:
    """Base class for ASR (Automatic Speech Recognition) implementations."""

    sep = " "   # join transcribe words with this character (" " for whisper_timestamped,
                # "" for faster-whisper because it emits the spaces when neeeded)

    def __init__(self, lan, modelsize=None, cache_dir=None, model_dir=None, logfile=sys.stderr):
        self.logfile = logfile

        self.transcribe_kargs = {}
        if lan == "auto":
            self.original_language = None
        else:
            self.original_language = lan

        self.model = self.load_model(modelsize, cache_dir, model_dir)

    def load_model(self, modelsize, cache_dir, model_dir=None):
        """Load the ASR model. Must be implemented by child classes."""
        raise NotImplementedError("must be implemented in the child class")

    def transcribe(self, audio, init_prompt=""):
        """Transcribe audio. Must be implemented by child classes."""
        raise NotImplementedError("must be implemented in the child class")

    def use_vad(self):
        """Enable Voice Activity Detection. Must be implemented by child classes."""
        raise NotImplementedError("must be implemented in the child class")

    def ts_words(self, segments):
        """Extract timestamped words from transcription segments."""
        raise NotImplementedError("must be implemented in the child class")

    def segments_end_ts(self, res):
        """Return the end timestamps of the segments."""
        raise NotImplementedError("must be implemented in the child class")
        
    def set_translate_task(self):
        """Configure the model for translation task instead of transcription."""
        raise NotImplementedError("must be implemented in the child class")