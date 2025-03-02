#!/usr/bin/env python3
import argparse
import socket
import pyaudio
import numpy as np
import threading
import line_packet
import time
import sys

def parse_args():
    parser = argparse.ArgumentParser(description="Client for whisper_streaming server")
    parser.add_argument("--host", type=str, default="localhost", help="Server hostname")
    parser.add_argument("--port", type=int, default=43007, help="Server port")
    parser.add_argument("--format", type=str, choices=["raw", "timestamp"], default="timestamp",
                        help="Output format: 'raw' or 'timestamp' (with timestamps)")
    parser.add_argument("--chunk-size", type=int, default=1024, help="Audio chunk size")
    return parser.parse_args()

class WhisperClient:
    def __init__(self, host, port, chunk_size=1024, format_type="timestamp"):
        """
        Initialize the whisper client
        
        Args:
            host: Server hostname
            port: Server port
            chunk_size: Audio chunk size
            format_type: Output format type ("raw" or "timestamp")
        """
        self.host = host
        self.port = port
        self.format_type = format_type
        
        # Audio recording settings
        self.chunk_size = chunk_size
        self.sample_rate = 16000  # Must match server's expected rate
        self.channels = 1         # Mono audio
        self.audio_format = pyaudio.paInt16
        self.is_recording = False
        
        self.audio = None
        self.socket = None
    
    def connect(self):
        """Connect to the server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            print(f"Connected to server at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Error connecting to server: {e}")
            return False
    
    def start_recording(self):
        """Start recording audio from default input device"""
        if self.is_recording:
            return
        
        self.is_recording = True
        self.audio = pyaudio.PyAudio()
        
        # Start the receiver thread
        self.receiver_thread = threading.Thread(target=self.receive_transcripts)
        self.receiver_thread.daemon = True
        self.receiver_thread.start()
        
        # Open audio stream
        self.stream = self.audio.open(
            format=self.audio_format,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )
        
        print("Recording started. Press Ctrl+C to stop.")
        
        try:
            while self.is_recording:
                # Read audio from microphone
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                
                # Send raw audio to server
                if self.socket:
                    try:
                        self.socket.sendall(data)
                    except (BrokenPipeError, ConnectionResetError):
                        print("Connection to server lost")
                        self.is_recording = False
                        break
        except KeyboardInterrupt:
            print("Recording stopped by user")
        finally:
            self.stop_recording()
    
    def receive_transcripts(self):
        """Receive and display transcripts from server"""
        while self.is_recording and self.socket:
            try:
                lines = line_packet.receive_lines(self.socket)
                if lines:
                    for line in lines:
                        if not line:
                            continue
                        
                        if self.format_type == "timestamp":
                            # Format with timestamps: "start_ms end_ms text"
                            parts = line.split(' ', 2)
                            if len(parts) >= 3:
                                start_ms, end_ms, text = parts
                                # Convert timestamps from milliseconds to seconds
                                start_s = float(start_ms) / 1000
                                end_s = float(end_ms) / 1000
                                print(f"[{start_s:.1f}s - {end_s:.1f}s] {text}")
                            else:
                                print(line)
                        else:
                            # Raw format - just print the transcript text
                            print(line)
                        print("\n")
                        sys.stdout.flush()
            except Exception as e:
                if self.is_recording:
                    print(f"Error receiving transcript: {e}")
                break
    
    def stop_recording(self):
        """Stop recording and clean up resources"""
        self.is_recording = False
        
        # Close audio stream and PyAudio
        if hasattr(self, 'stream'):
            self.stream.stop_stream()
            self.stream.close()
        
        if self.audio:
            self.audio.terminate()
        
        # Close socket connection
        if self.socket:
            self.socket.close()

def main():
    args = parse_args()
    
    client = WhisperClient(args.host, args.port, args.chunk_size, args.format)
    
    if client.connect():
        try:
            client.start_recording()
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            client.stop_recording()

if __name__ == "__main__":
    main()