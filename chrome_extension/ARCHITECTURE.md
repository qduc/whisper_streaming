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
