#!/usr/bin/env python3
import sys
import logging
import io
import soundfile
import librosa
import numpy as np
import json
from line_packet import send_one_line, receive_lines
import asyncio
import inspect

logger = logging.getLogger(__name__)

class Connection:
    '''it wraps conn object'''
    PACKET_SIZE = 32000*5*60 # 5 minutes # was: 65536

    def __init__(self, conn):
        self.conn = conn
        self.last_line = ""

        self.conn.setblocking(True)

    def send(self, line):
        '''it doesn't send the same line twice, because it was problematic in online-text-flow-events'''
        if line == self.last_line:
            return
        send_one_line(self.conn, line)
        self.last_line = line

    def receive_lines(self):
        in_line = receive_lines(self.conn)
        return in_line

    def non_blocking_receive_audio(self):
        try:
            r = self.conn.recv(self.PACKET_SIZE)
            return r
        except ConnectionResetError:
            return None

class BaseServerProcessor:
    """Base class for server processors that handle audio processing and transcription"""
    
    SAMPLING_RATE = 16000
    
    def __init__(self, connection, online_asr_proc, min_chunk):
        self.connection = connection
        self.online_asr_proc = online_asr_proc
        self.min_chunk = min_chunk
        self.last_end = None
        self.is_first = True
        
    async def _get_audio_data(self, raw_bytes_coro_or_bytes):
        """Handle the result of non_blocking_receive_audio which might be a coroutine or bytes"""
        if inspect.iscoroutine(raw_bytes_coro_or_bytes):
            # If it's a coroutine, await it
            raw_bytes = await raw_bytes_coro_or_bytes
        else:
            # Otherwise, use it directly
            raw_bytes = raw_bytes_coro_or_bytes
            
        if not raw_bytes:
            return None
            
        sf = soundfile.SoundFile(io.BytesIO(raw_bytes), channels=1, endian="LITTLE",
                                samplerate=self.SAMPLING_RATE, subtype="PCM_16", format="RAW")
        audio, _ = librosa.load(sf, sr=self.SAMPLING_RATE, dtype=np.float32)
        return audio
        
    def receive_audio_chunk(self):
        """Receive audio chunks from the connection - synchronous version"""
        # receive all audio that is available by this time
        # blocks operation if less than self.min_chunk seconds is available
        # unblocks if connection is closed or a chunk is available
        out = []
        minlimit = self.min_chunk * self.SAMPLING_RATE
        while sum(len(x) for x in out) < minlimit:
            result = self.connection.non_blocking_receive_audio()
            
            # Check if the result is a coroutine
            if inspect.iscoroutine(result):
                # This is a synchronous method, but we got a coroutine.
                # We cannot use asyncio.run() inside an event loop.
                # Instead, we need to signal to the caller that they
                # should use the async version of this method.
                raise RuntimeError(
                    "Received coroutine from non_blocking_receive_audio in synchronous context. "
                    "Use process_async() instead of process() for asynchronous connections."
                )
            else:
                # Process the bytes directly
                if not result:
                    break
                try:
                    sf = soundfile.SoundFile(io.BytesIO(result), channels=1, endian="LITTLE",
                                            samplerate=self.SAMPLING_RATE, subtype="PCM_16", format="RAW")
                    audio, _ = librosa.load(sf, sr=self.SAMPLING_RATE, dtype=np.float32)
                    out.append(audio)
                except Exception as e:
                    logger.error(f"Error processing audio data: {e}")
                    break
            
        if not out:
            return None
        conc = np.concatenate(out)
        if self.is_first and len(conc) < minlimit:
            return None
        self.is_first = False
        return conc
    
    async def receive_audio_chunk_async(self):
        """Async version of receive_audio_chunk"""
        out = []
        minlimit = self.min_chunk * self.SAMPLING_RATE
        while sum(len(x) for x in out) < minlimit:
            result = self.connection.non_blocking_receive_audio()
            audio = await self._get_audio_data(result)
            if audio is None:
                break
            out.append(audio)
        
        if not out:
            return None
        conc = np.concatenate(out)
        if self.is_first and len(conc) < minlimit:
            return None
        self.is_first = False
        return np.concatenate(out)
        
    def format_output_transcript(self, o):
        """Format the transcript output with timestamps"""
        # output format in stdout is like:
        # 0 1720 Takhle to je
        # - the first two words are:
        #    - beg and end timestamp of the text segment, as estimated by Whisper model. The timestamps are not accurate, but they're useful anyway
        # - the next words: segment transcript

        # This function differs from whisper_online.output_transcript in the following:
        # succeeding [beg,end] intervals are not overlapping because ELITR protocol (implemented in online-text-flow events) requires it.
        # Therefore, beg, is max of previous end and current beg outputed by Whisper.
        # Usually it differs negligibly, by appx 20 ms.

        if o[0] is not None:
            beg, end = o[0]*1000, o[1]*1000
            if self.last_end is not None:
                beg = max(beg, self.last_end)

            self.last_end = end
            print("%1.0f %1.0f %s" % (beg, end, o[2]))
            return "%1.0f %1.0f %s" % (beg, end, o[2])
        else:
            logger.debug("No text in this segment")
            return None
            
    async def send_result(self, o):
        """Process and send the result to the client in JSON format"""
        if o[0] is not None:
            beg, end = o[0]*1000, o[1]*1000
            if self.last_end is not None:
                beg = max(beg, self.last_end)
            self.last_end = end
            
            # Log the transcript to console
            text = o[2].replace("  ", " ")
            print("%1.0f %1.0f %s" % (beg, end, text), flush=True, file=sys.stderr)
            
            # Format as JSON for all clients
            msg = json.dumps({
                "type": "transcription",
                "start": beg,
                "end": end,
                "text": text
            })
            
            if hasattr(self.connection, 'websocket'):
                await self.connection.send(msg)
            else:
                self.connection.send(msg)
        else:
            logger.debug("No text in this segment")
            
    def process(self):
        """Main processing loop"""
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
                    
            # Finish processing any remaining audio
            # o = self.online_asr_proc.finish()
            # self.send_result(o)
        except Exception as e:
            logger.error(f"Error in processor: {e}")
            raise

    async def process_async(self):
        """Asynchronous processing loop"""
        self.online_asr_proc.init()
        try:
            while True:
                a = await self.receive_audio_chunk_async()
                if a is None:
                    break
                self.online_asr_proc.insert_audio_chunk(a)
                o = self.online_asr_proc.process_iter()
                try:
                    await self.send_result(o)
                except Exception as e:
                    logger.error(f"Connection error: {e}")
                    break
        except Exception as e:
            logger.error(f"Error in processor: {e}")
            raise
