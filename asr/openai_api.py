import io
import math
import logging
import soundfile as sf
from openai import OpenAI
from .base import ASRBase

logger = logging.getLogger(__name__)

class OpenaiApiASR(ASRBase):
    """Uses OpenAI's Whisper API for audio transcription."""

    def __init__(self, lan=None, temperature=0, logfile=None):
        self.logfile = logfile
        self.modelname = "whisper-1"  
        self.original_language = None if lan == "auto" else lan  # ISO-639-1 language code
        self.response_format = "verbose_json" 
        self.temperature = temperature
        self.use_vad_opt = False
        self.task = "transcribe"  # reset in set_translate_task
        super().__init__(lan=lan, logfile=logfile)

    def load_model(self, modelsize=None, cache_dir=None, model_dir=None):
        self.client = OpenAI()
        self.transcribed_seconds = 0  # for logging how many seconds were processed by API, to know the cost
        return self.client

    def transcribe(self, audio_data, prompt=None, *args, **kwargs):
        # Write the audio data to a buffer
        buffer = io.BytesIO()
        buffer.name = "temp.wav"
        sf.write(buffer, audio_data, samplerate=16000, format='WAV', subtype='PCM_16')
        buffer.seek(0)  # Reset buffer's position to the beginning

        self.transcribed_seconds += math.ceil(len(audio_data)/16000)  # it rounds up to the whole seconds

        params = {
            "model": self.modelname,
            "file": buffer,
            "response_format": self.response_format,
            "temperature": self.temperature,
            "timestamp_granularities": ["word", "segment"]
        }
        if self.task != "translate" and self.original_language:
            params["language"] = self.original_language
        if prompt:
            params["prompt"] = prompt

        if self.task == "translate":
            proc = self.client.audio.translations
        else:
            proc = self.client.audio.transcriptions

        # Process transcription/translation
        transcript = proc.create(**params)
        logger.debug(f"OpenAI API processed accumulated {self.transcribed_seconds} seconds")

        return transcript

    def ts_words(self, segments):
        no_speech_segments = []
        if self.use_vad_opt:
            for segment in segments.segments:
                # TODO: threshold can be set from outside
                if segment["no_speech_prob"] > 0.8:
                    no_speech_segments.append((segment.get("start"), segment.get("end")))

        o = []
        for word in segments.words:
            start = word.start
            end = word.end
            if any(s[0] <= start <= s[1] for s in no_speech_segments):
                continue
            o.append((start, end, word.word))
        return o

    def segments_end_ts(self, res):
        return [s.end for s in res.words]

    def use_vad(self):
        self.use_vad_opt = True

    def set_translate_task(self):
        self.task = "translate"