import sys
import logging
import openai

logger = logging.getLogger(__name__)

class TranslatedServerProcessor:
    def __init__(self, c, online_asr_proc, min_chunk, target_language='en'):
        # No import of ServerProcessor
        self.connection = c
        self.online_asr_proc = online_asr_proc
        self.min_chunk = min_chunk
        self.last_end = None
        self.is_first = True
        self.target_language = target_language
        
        # Initialize for audio processing
        self.SAMPLING_RATE = 16000
        
    def translate_text(self, text):
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Translate the following speech transcript to {self.target_language}. Output only the translated text without any explanations."},
                {"role": "user", "content": text}
            ],
            max_tokens=1000
        )
        return response.choices[0].message.content.strip()

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
            
            # Translate the text
            translated_text = self.translate_text(o[2])
            
            # Use translated text instead of original
            print("%1.0f %1.0f %s (translated from: %s)" % (beg, end, translated_text, o[2]), flush=True, file=sys.stderr)
            msg = "%1.0f %1.0f %s" % (beg, end, translated_text)
            
            if msg is not None:
                self.connection.send(msg)
        else:
            logger.debug("No text in this segment")
            
    def process(self):
        self.online_asr_proc.init()
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
