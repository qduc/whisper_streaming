# System Architecture: Live Audio Transcription with Whisper

## Overview
This system provides real-time audio capture, transcription, and optional translation using OpenAI's Whisper models. It consists of two main components:

1. **Server**: A Python-based WebSocket/TCP server that processes audio streams and returns transcriptions
2. **Chrome Extension**: A browser extension that captures tab audio and displays transcriptions in an overlay

## Server Components

### 1. **Whisper Online Core (`whisper_online.py`)**
- Implements core ASR (Automatic Speech Recognition) functionality
- Supports multiple Whisper backends:
  - `faster-whisper`: Optimized for NVIDIA GPUs
  - `whisper_timestamped`: Original implementation
  - `mlx-whisper`: Optimized for Apple Silicon
  - `openai-api`: Uses OpenAI's API for transcription
- Provides `OnlineASRProcessor` for managing audio buffers and transcription hypotheses
- Implements VAD (Voice Activity Detection) for better voice segmentation

### 2. **Server Base (`server_base.py`)**
- Provides base connection handling for both TCP and WebSocket protocols
- Defines `BaseServerProcessor` with common audio processing methods
- Handles audio reception and conversion into numpy arrays

### 3. **Server Implementation (`whisper_online_server.py`)**
- Command-line interface with configurable options
- Supports both WebSocket and TCP connections
- Can be run with different transcription models and settings
- Optional translation capabilities using various models (Gemini or OpenAI)

### 4. **WebSocket Connection (`websocket_connection.py`)**
- Implements WebSocket protocol handling
- Provides `WebSocketServerProcessor` for asynchronous audio processing
- Formats and sends JSON responses to clients

### 5. **Server Processors (`server_processors.py`)**
- Processes audio chunks and manages transcription workflow
- Optional translation capabilities for multilingual support
- Formats and sends transcription results to clients

## Chrome Extension Components

### 1. **Manifest File (`manifest.json`)**
- Declares required permissions: `tabCapture`, `activeTab`, `storage`, `scripting`
- Defines background, content script, and popup UI
- Specifies host permissions for WebSocket API connections

### 2. **Background Service Worker (`background.js`)**
- Establishes and maintains WebSocket connection to the server
- Uses offscreen document API for tab audio capture
- Routes transcription data between server and content scripts
- Manages extension state and UI updates

### 3. **Offscreen Document (`offscreen.html`, `offscreen.js`)**
- Handles audio capture using Chrome's Tab Capture API
- Processes raw audio into appropriate format for transmission
- Sends audio chunks to background script

### 4. **WebSocket Client (`websocketClient.js`)**
- Manages WebSocket connection to the transcription server
- Handles connection errors and reconnection logic
- Sends audio data and receives transcriptions

### 5. **Content Script (`content.js`)**
- Creates and manages floating overlay for displaying transcriptions
- Updates transcription text in real-time
- Supports customizable appearance (opacity, text size)
- Provides draggable overlay positioning

### 6. **Popup UI (`popup.html`, `popup.js`)**
- Provides controls to start/stop transcription
- Displays connection status information
- Offers settings for customizing the overlay appearance
- Saves user preferences using Chrome storage API

## Workflow

1. **User Activates Transcription**
   - Clicks extension popup button or uses keyboard shortcut
   - Background script initiates WebSocket connection to server

2. **Audio Capture Begins**
   - Background script sets up offscreen document for tab audio capture
   - Audio stream is established using `chrome.tabCapture.getMediaStreamId`
   - Audio is processed and formatted for transmission

3. **Streaming to WebSocket Server**
   - Audio frames are sent in chunks to the WebSocket server
   - Server buffers audio and processes it through Whisper ASR
   - Voice activity detection optimizes transcription timing

4. **Server Processing**
   - Server applies VAD to detect speech segments
   - Speech segments are transcribed using selected Whisper model
   - Optional translation processing for multilingual support

5. **Transcription Returned**
   - Server sends JSON formatted transcriptions back via WebSocket
   - Includes timestamps and text content

6. **Overlay Displays Transcription**
   - Content script receives transcription data
   - Updates floating overlay with transcribed text
   - Applies user-defined styling preferences

7. **User Stops Transcription**
   - Clicking popup button stops the transcription process
   - WebSocket connection closes
   - Audio capture terminates
   - Overlay is hidden