class VACOnlineASRProcessor(OnlineASRProcessor):
    '''Wraps OnlineASRProcessor with VAC (Voice Activity Controller).

    It works the same way as OnlineASRProcessor: it receives chunks of audio (e.g. 0.04 seconds),
    it runs VAD and continuously detects whether there is speech or not.
    When it detects end of speech (non-voice for 500ms), it makes OnlineASRProcessor to end the utterance immediately.
    '''

    def __init__(self, online_chunk_size, *a, **kw):
        self.online_chunk_size = online_chunk_size

        self.online = OnlineASRProcessor(*a, **kw)

        # VAC:
        import torch
        model, _ = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad'
        )
        from silero_vad_iterator import FixedVADIterator
        self.vac = FixedVADIterator(model)  # we use the default options there: 500ms silence, 100ms padding, etc.

        self.logfile = self.online.logfile
        self.init()

    def init(self):
        self.online.init()
        self.vac.reset_states()
        self.current_online_chunk_buffer_size = 0

        self.is_currently_final = False

        self.status = None  # or "voice" or "nonvoice"
        self.audio_buffer = np.array([],dtype=np.float32)
        self.buffer_offset = 0  # in frames

    def clear_buffer(self):
        self.buffer_offset += len(self.audio_buffer)
        self.audio_buffer = np.array([],dtype=np.float32)


    def insert_audio_chunk(self, audio):
        res = self.vac(audio)
        self.audio_buffer = np.append(self.audio_buffer, audio)

        if res is not None:
            frame = list(res.values())[0]-self.buffer_offset
            if 'start' in res and 'end' not in res:
                self.status = 'voice'
                send_audio = self.audio_buffer[frame:]
                self.online.init(offset=(frame+self.buffer_offset)/self.SAMPLING_RATE)
                self.online.insert_audio_chunk(send_audio)
                self.current_online_chunk_buffer_size += len(send_audio)
                self.clear_buffer()
            elif 'end' in res and 'start' not in res:
                self.status = 'nonvoice'
                send_audio = self.audio_buffer[:frame]
                self.online.insert_audio_chunk(send_audio)
                self.current_online_chunk_buffer_size += len(send_audio)
                self.is_currently_final = True
                self.clear_buffer()
            else:
                beg = res["start"]-self.buffer_offset
                end = res["end"]-self.buffer_offset
                self.status = 'nonvoice'
                send_audio = self.audio_buffer[beg:end]
                self.online.init(offset=(beg+self.buffer_offset)/self.SAMPLING_RATE)
                self.online.insert_audio_chunk(send_audio)
                self.current_online_chunk_buffer_size += len(send_audio)
                self.is_currently_final = True
                self.clear_buffer()
        else:
            if self.status == 'voice':
                self.online.insert_audio_chunk(self.audio_buffer)
                self.current_online_chunk_buffer_size += len(self.audio_buffer)
                self.clear_buffer()
            else:
                # We keep 1 second because VAD may later find start of voice in it.
                # But we trim it to prevent OOM.
                self.buffer_offset += max(0,len(self.audio_buffer)-self.SAMPLING_RATE)
                self.audio_buffer = self.audio_buffer[-self.SAMPLING_RATE:]


    def process_iter(self):
        if self.is_currently_final:
            logger.debug(f"finalizing online processing, status: {self.status}")
            return self.finish()
        elif self.current_online_chunk_buffer_size > self.SAMPLING_RATE*self.online_chunk_size:
            self.current_online_chunk_buffer_size = 0
            ret = self.online.process_iter()
            return ret
        else:
            if hasattr(self, '_last_status') and self._last_status == self.status:
                pass  # Don't log if status hasn't changed
            else:
                logger.debug(f"no online update, only VAD, status: {self.status}")
                self._last_status = self.status
            return (None, None, "")

    def finish(self):
        ret = self.online.finish()
        self.current_online_chunk_buffer_size = 0
        self.is_currently_final = False
        return ret