#!/usr/bin/env python3
import numpy as np
import librosa
from functools import lru_cache

SAMPLING_RATE = 16000

@lru_cache(10**6)
def load_audio(fname):
    """Load an audio file into memory.
    
    Args:
        fname (str): Path to the audio file
        
    Returns:
        numpy.ndarray: Audio data as a numpy array
    """
    a, _ = librosa.load(fname, sr=SAMPLING_RATE, dtype=np.float32)
    return a

def load_audio_chunk(fname, beg, end):
    """Load a chunk of an audio file into memory.
    
    Args:
        fname (str): Path to the audio file
        beg (float): Start time in seconds
        end (float): End time in seconds
        
    Returns:
        numpy.ndarray: Audio chunk data as a numpy array
    """
    audio = load_audio(fname)
    beg_s = int(beg * SAMPLING_RATE)
    end_s = int(end * SAMPLING_RATE)
    return audio[beg_s:end_s]