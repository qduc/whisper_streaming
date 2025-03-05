# Chrome Extension Architecture: Live Audio Transcription  

## Overview  
This Chrome extension captures audio from the current tab, transmits it to a WebSocket API for transcription, and displays the resulting text in an overlay.  

## Components  

### 1. **Manifest File (manifest.json)**  
- Declares permissions: `tabCapture`, `activeTab`, `storage`, and `scripting`.  
- Defines the background script, content script, and popup UI.  
- Specifies required host permissions for the WebSocket API.  

### 2. **Background Service Worker (background.js)**  
- Listens for activation via the extension’s UI or a keyboard shortcut.  
- Initiates tab audio capture using `chrome.tabCapture.capture`.  
- Establishes a connection with the WebSocket API.  
- Streams raw audio data chunks to the WebSocket server.  
- Forwards received transcriptions to the content script for display.  

### 3. **Content Script (content.js)**  
- Injects a floating semi-transparent overlay at the bottom of the active tab.  
- Listens for transcription updates from the background script via `chrome.runtime.onMessage`.  
- Updates the text in the overlay in real time.  

### 4. **Popup UI (popup.html & popup.js)**  
- Provides a button to start/stop transcription.  
- Displays connection status (e.g., "Listening…" or "Disconnected").  
- Saves and loads user preferences (e.g., text size, transparency) using `chrome.storage.sync`.  

### 5. **Audio Processing (audioProcessor.js)**  
- Converts captured audio into an appropriate format for transmission.  
- Compresses or encodes the data as needed.  
- Sends audio data to the WebSocket API in small chunks.  

### 6. **WebSocket Communication (websocketClient.js)**  
- Establishes and maintains a WebSocket connection.  
- Manages error handling and reconnections if necessary.  
- Sends processed audio and receives the transcription.  
- Relays transcription data to the background script.  

## Workflow  

1. **User Activates Transcription**  
   - Clicks the extension popup button or uses a keyboard shortcut.  

2. **Audio Capture Begins**  
   - Background script calls `chrome.tabCapture.capture({audio: true})`.  
   - Retrieves and processes the audio stream.  

3. **Streaming to WebSocket API**  
   - Audio frames are processed and sent via WebSocket.  

4. **Transcription Received**  
   - WebSocket API returns the processed text.  
   - Background script forwards transcription to the content script.  

5. **Overlay Displays Transcription**  
   - Content script updates the floating text overlay.  
   - Text dynamically updates as new transcriptions arrive.  

6. **User Stops Transcription**  
   - Clicking the popup button or closing the tab stops audio capture.  
   - WebSocket connection closes.  
