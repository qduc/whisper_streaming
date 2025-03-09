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

# Overlay Transcription System Specification

## Overview

The Whisper Streaming Overlay is a Chrome extension component that displays real-time speech transcriptions as a floating overlay on web pages. It provides a non-intrusive, customizable caption display that automatically shows and hides based on transcription activity.

## Core Components

### 1. Overlay Management

- **Creation & Display**: Dynamically creates a draggable overlay element that floats above webpage content
- **Positioning**: Supports both centered positioning and custom user-defined positions
- **Visibility Control**: Automatically shows when new transcription text arrives and hides after a configurable period of inactivity

### 2. Text Processing & Display

- **Buffer System**: Maintains a multi-line text buffer to display recent transcription history
- **Text Accumulation**: Intelligently collects and processes text segments before display
- **Display Logic**: Updates the visual display based on configurable thresholds for text length and timing

### 3. User Interaction

- **Draggable Interface**: Allows users to reposition the overlay anywhere on the screen
- **Position Memory**: Remembers overlay position between sessions
- **Responsive Design**: Adapts to window resizing while maintaining visibility

## Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `textSize` | Font size for display text (small/medium/large) | medium |
| `overlayOpacity` | Transparency level of the overlay | 0.8 |
| `numOfLines` | Number of text lines to display in history buffer | 3 |
| `minLengthToDisplay` | Minimum text length before updating display | 30 characters |
| `maxIdleTime` | Maximum wait time before displaying accumulated text | 1.5 seconds |
| `overlayHideTimeout` | Time before hiding inactive overlay | 15 seconds |

## Communication Interface

The overlay communicates with the extension background script via Chrome messaging:

| Message Action | Description |
|---------------|-------------|
| `updateTranscription` | Processes new transcription text |
| `showOverlay` | Explicitly displays overlay and applies settings |
| `hideOverlay` | Explicitly hides overlay and clears buffer |
| `settingsUpdated` | Updates configuration parameters |

## Visual Design

- Semi-transparent black background with rounded corners
- Primarily white text with grayed-out previous lines
- Automatically sized based on content with maximum width constraints
- Unobtrusive appearance with smooth transitions

## Technical Behavior

1. **Initialization**:
   - Creates overlay elements but keeps them hidden
   - Loads user settings from Chrome storage
   - Sets up message listeners

2. **Text Processing**:
   - Accumulates text until a threshold is reached
   - Updates display when text reaches minimum length or max idle time
   - Maintains buffer of recent text lines with newest at bottom

3. **Auto-hide Behavior**:
   - Shows overlay when receiving transcription
   - Resets hide timer whenever new content arrives
   - Automatically hides overlay after configurable timeout period

4. **Drag Functionality**:
   - Transitions from centered to absolute positioning when dragged
   - Constrains overlay within viewport boundaries
   - Persists position between visibility toggles

## Browser Compatibility

- Designed for Chrome browser environment
- Utilizes Chrome extension API for storage and messaging

## Performance Considerations

- Minimal DOM manipulation for efficient updates
- Event throttling to prevent performance issues during dragging
- Cleanup handling for proper extension deactivation
