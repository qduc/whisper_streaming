#!/usr/bin/env python3
from whisper_online import *

import sys
import argparse
import os
import logging
import numpy as np
import openai  # Added for translation functionality
import socket

logger = logging.getLogger(__name__)
parser = argparse.ArgumentParser()

# server options
parser.add_argument("--host", type=str, default='localhost')
parser.add_argument("--port", type=int, default=43007)
parser.add_argument("--warmup-file", type=str, dest="warmup_file", 
        help="The path to a speech audio wav file to warm up Whisper so that the very first chunk processing is fast. It can be e.g. https://github.com/ggerganov/whisper.cpp/raw/master/samples/jfk.wav .")
# Translation options
parser.add_argument("--translate", action="store_true", help="Enable translation of transcript")
parser.add_argument("--target-language", type=str, default="en", help="Target language for translation")
parser.add_argument("--translation-interval", type=float, default=3.0, 
                    help="Minimum time in seconds between translation API calls")
parser.add_argument("--max-buffer-time", type=float, default=10.0, 
                    help="Maximum time to buffer text before forcing translation")
parser.add_argument("--min-text-length", type=int, default=20,
                    help="Minimum text length to consider for translation")
parser.add_argument("--translation-model", type=str, default="gpt-4o-mini",
                    help="Model to use for translation (e.g. gpt-4o-mini, gpt-3.5-turbo)")
parser.add_argument("--use-gemini", action="store_true",
                    help="Use Gemini 2.0 Flash model for translation (requires GEMINI_API_KEY env variable)")

# options from whisper_online
add_shared_args(parser)
args = parser.parse_args()

set_logging(args,logger,other="")

# setting whisper object by args 

SAMPLING_RATE = 16000

size = args.model
language = args.lan
asr, online = asr_factory(args)
min_chunk = args.min_chunk_size

# warm up the ASR because the very first transcribe takes more time than the others. 
# Test results in https://github.com/ufal/whisper_streaming/pull/81
msg = "Whisper is not warmed up. The first chunk processing may take longer."
if args.warmup_file:
    if os.path.isfile(args.warmup_file):
        a = load_audio_chunk(args.warmup_file,0,1)
        asr.transcribe(a)
        logger.info("Whisper is warmed up.")
    else:
        logger.critical("The warm up file is not available. "+msg)
        sys.exit(1)
else:
    logger.warning(msg)


######### Server objects

import line_packet

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
        line_packet.send_one_line(self.conn, line)
        self.last_line = line

    def receive_lines(self):
        in_line = line_packet.receive_lines(self.conn)
        return in_line

    def non_blocking_receive_audio(self):
        try:
            r = self.conn.recv(self.PACKET_SIZE)
            return r
        except ConnectionResetError:
            return None


import io
import soundfile

# wraps socket and ASR object, and serves one client connection. 
# next client should be served by a new instance of this object
class ServerProcessor:

    def __init__(self, c, online_asr_proc, min_chunk):
        self.connection = c
        self.online_asr_proc = online_asr_proc
        self.min_chunk = min_chunk

        self.last_end = None

        self.is_first = True

    def receive_audio_chunk(self):
        # receive all audio that is available by this time
        # blocks operation if less than self.min_chunk seconds is available
        # unblocks if connection is closed or a chunk is available
        out = []
        minlimit = self.min_chunk*SAMPLING_RATE
        while sum(len(x) for x in out) < minlimit:
            raw_bytes = self.connection.non_blocking_receive_audio()
            if not raw_bytes:
                break
#            print("received audio:",len(raw_bytes), "bytes", raw_bytes[:10])
            sf = soundfile.SoundFile(io.BytesIO(raw_bytes), channels=1,endian="LITTLE",samplerate=SAMPLING_RATE, subtype="PCM_16",format="RAW")
            audio, _ = librosa.load(sf,sr=SAMPLING_RATE,dtype=np.float32)
            out.append(audio)
        if not out:
            return None
        conc = np.concatenate(out)
        if self.is_first and len(conc) < minlimit:
            return None
        self.is_first = False
        return np.concatenate(out)

    def format_output_transcript(self,o):
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
            beg, end = o[0]*1000,o[1]*1000
            if self.last_end is not None:
                beg = max(beg, self.last_end)

            self.last_end = end
            print("%1.0f %1.0f %s" % (beg,end,o[2]),flush=True,file=sys.stderr)
            return "%1.0f %1.0f %s" % (beg,end,o[2])
        else:
            logger.debug("No text in this segment")
            return None

    def send_result(self, o):
        msg = self.format_output_transcript(o)
        if msg is not None:
            self.connection.send(msg)

    def process(self):
        # handle one client connection
        self.online_asr_proc.init()
        while True:
            a = self.receive_audio_chunk()
            if a is None:
                break
            self.online_asr_proc.insert_audio_chunk(a)
            o = online.process_iter()
            try:
                self.send_result(o)
            except BrokenPipeError:
                logger.info("broken pipe -- connection closed?")
                break

#        o = online.finish()  # this should be working
#        self.send_result(o)

# server loop

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    # Set SO_REUSEADDR option to avoid "Address already in use" error
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((args.host, args.port))
    s.listen(1)
    logger.info('Listening on'+str((args.host, args.port)))
    while True:
        conn, addr = s.accept()
        logger.info('Connected to client on {}'.format(addr))
        connection = Connection(conn)
        
        # Use the translation processor if translation is enabled
        if args.translate:
            # Import when needed, avoiding circular import
            from translated_server import TranslatedServerProcessor
            logger.info(f'Translation enabled. Target language: {args.target_language}')
            
            # Create translation processor with configurable parameters
            proc = TranslatedServerProcessor(
                connection, 
                online, 
                args.min_chunk_size, 
                args.target_language,
                model=args.translation_model,
                use_gemini=args.use_gemini
            )
            
            # Set additional translation parameters if provided
            proc.translation_interval = args.translation_interval
            proc.max_buffer_time = args.max_buffer_time
            proc.min_text_length = args.min_text_length
            
            # Log model selection
            if args.use_gemini:
                gemini_api_key = os.environ.get("GEMINI_API_KEY")
                if gemini_api_key:
                    logger.info(f'Using Gemini 2.0 Flash model for translation')
                else:
                    logger.warning('GEMINI_API_KEY environment variable not set. Will fall back to OpenAI.')
            else:
                logger.info(f'Using OpenAI model: {args.translation_model}')
            
            logger.info(f'Translation settings: interval={proc.translation_interval}s, '
                        f'max_buffer={proc.max_buffer_time}s, '
                        f'min_length={proc.min_text_length} chars')
        else:
            proc = ServerProcessor(connection, online, args.min_chunk_size)
            
        proc.process()
        conn.close()
        logger.info('Connection to client closed')
logger.info('Connection closed, terminating.')
