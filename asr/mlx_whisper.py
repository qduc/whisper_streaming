import logging
from .base import ASRBase
import mlx.core as mx

logger = logging.getLogger(__name__)

class MLXWhisper(ASRBase):
    """Uses MLX Whisper library as the backend, optimized for Apple Silicon.
    Models available: https://huggingface.co/collections/mlx-community/whisper-663256f9964fbb1177db93dc
    Significantly faster than faster-whisper (without CUDA) on Apple M1.
    """

    sep = " "

    def load_model(self, modelsize=None, cache_dir=None, model_dir=None):
        """Loads the MLX-compatible Whisper model.

        Args:
            modelsize (str, optional): The size or name of the Whisper model to load. 
                If provided, it will be translated to an MLX-compatible model path.
                Example: "large-v3-turbo" -> "mlx-community/whisper-large-v3-turbo".
            cache_dir (str, optional): Path to the directory for caching models. 
                **Note**: This is not supported by MLX Whisper and will be ignored.
            model_dir (str, optional): Direct path to a custom model directory. 
                If specified, it overrides the modelsize parameter.
        """
        from mlx_whisper.transcribe import ModelHolder, transcribe
        
        if model_dir is not None:
            logger.debug(f"Loading whisper model from model_dir {model_dir}. modelsize parameter is not used.")
            model_size_or_path = model_dir
        elif modelsize is not None:
            model_size_or_path = self.translate_model_name(modelsize)
            logger.debug(f"Loading whisper model {modelsize}. You use mlx whisper, so {model_size_or_path} will be used.")
        
        self.model_size_or_path = model_size_or_path
        
        # Note: ModelHolder.get_model loads the model into a static class variable, 
        # making it a global resource. This means:
        # - Only one model can be loaded at a time; switching models requires reloading.
        # - This approach may not be suitable for scenarios requiring multiple models simultaneously,
        #   such as using whisper-streaming as a module with varying model sizes.
        dtype = mx.float16  # Default to mx.float16
        ModelHolder.get_model(model_size_or_path, dtype)  # Model is preloaded to avoid reloading during transcription
        
        return transcribe
    
    def translate_model_name(self, model_name):
        """Translates a given model name to its corresponding MLX-compatible model path."""
        # Dictionary mapping model names to MLX-compatible paths
        model_mapping = {
            "tiny.en": "mlx-community/whisper-tiny.en-mlx",
            "tiny": "mlx-community/whisper-tiny-mlx",
            "base.en": "mlx-community/whisper-base.en-mlx",
            "base": "mlx-community/whisper-base-mlx",
            "small.en": "mlx-community/whisper-small.en-mlx",
            "small": "mlx-community/whisper-small-mlx",
            "medium.en": "mlx-community/whisper-medium.en-mlx",
            "medium": "mlx-community/whisper-medium-mlx",
            "large-v1": "mlx-community/whisper-large-v1-mlx",
            "large-v2": "mlx-community/whisper-large-v2-mlx",
            "large-v3": "mlx-community/whisper-large-v3-mlx",
            "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
            "large": "mlx-community/whisper-large-mlx"
        }

        mlx_model_path = model_mapping.get(model_name)
        if mlx_model_path:
            return mlx_model_path
        else:
            raise ValueError(f"Model name '{model_name}' is not recognized or not supported.")
    
    def transcribe(self, audio, init_prompt=""):
        segments = self.model(
            audio,
            language=self.original_language,
            initial_prompt=init_prompt,
            word_timestamps=True,
            condition_on_previous_text=True,
            path_or_hf_repo=self.model_size_or_path,
            **self.transcribe_kargs
        )
        return segments.get("segments", [])

    def ts_words(self, segments):
        """Extract timestamped words from transcription segments and skips words with high no-speech probability."""
        return [
            (word["start"], word["end"], word["word"])
            for segment in segments
            for word in segment.get("words", [])
            if segment.get("no_speech_prob", 0) <= 0.9
        ]
    
    def segments_end_ts(self, res):
        return [s['end'] for s in res]

    def use_vad(self):
        self.transcribe_kargs["vad_filter"] = True

    def set_translate_task(self):
        self.transcribe_kargs["task"] = "translate"