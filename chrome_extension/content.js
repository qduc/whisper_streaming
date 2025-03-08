// Global variables
let overlay = null;
let textContainer = null;
let isVisible = false;
let textBuffer = [];
let currentText = '';
let lastUpdateTime = 0;
let updateTimer = null;
let hideTimer = null;
// Add drag-related variables
let isDragging = false;
let dragOffset = { x: 0, y: 0 };
let overlayPosition = { left: '50%', top: '80%' }; // Store position as percentage

let currentSettings = {
  textSize: 'medium',
  overlayOpacity: 0.8,
  shortChunkThreshold: 15,   // Legacy setting
  longChunkThreshold: 80,    // Legacy setting
  maxLineLength: 100,        // Legacy setting
  numOfLines: 3,             // Default number of lines in the buffer
  minLengthToDisplay: 30,    // Minimum text length to display
  maxIdleTime: 1.5,          // Maximum idle time in seconds before displaying buffer
  overlayHideTimeout: 15     // Time in seconds before hiding overlay when idle
};

// Initialize when the content script loads
initialize();

function initialize() {
  // Create overlay elements but keep them hidden initially
  createOverlay();
  
  // Load user settings
  loadSettings();
  
  // Listen for messages from background script
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('Received message:', message);
    
    try {
      if (message.action === 'updateTranscription') {
        updateTranscriptionText(message);
      }
      else if (message.action === 'showOverlay') {
        console.log('Show overlay command received');
        if (message.settings) {
          console.log('Applying settings:', message.settings);
          currentSettings = {...currentSettings, ...message.settings};
          applySettings();
        }
        showOverlay();
      }
      else if (message.action === 'hideOverlay') {
        console.log('Hide overlay command received');
        hideOverlay();
      }
      else if (message.action === 'settingsUpdated') {
        console.log('Settings update received:', message.settings);
        currentSettings = {...currentSettings, ...message.settings};
        applySettings();
      }
      else {
        console.log('Unknown action received:', message.action);
      }
      
      // Return true to indicate async response handling if needed
      return true;
    } catch (error) {
      console.error('Error processing message:', error);
    }
  });
}

function loadSettings() {
  chrome.storage.sync.get('settings', (data) => {
    if (data.settings) {
      // Apply all saved settings
      if (data.settings.shortChunkThreshold) {
        currentSettings.shortChunkThreshold = data.settings.shortChunkThreshold;
      }
      if (data.settings.longChunkThreshold) {
        currentSettings.longChunkThreshold = data.settings.longChunkThreshold;
      }
      if (data.settings.maxLineLength) {
        currentSettings.maxLineLength = data.settings.maxLineLength;
      }
      if (data.settings.numOfLines) {
        currentSettings.numOfLines = data.settings.numOfLines;
      }
      if (data.settings.minLengthToDisplay) {
        currentSettings.minLengthToDisplay = data.settings.minLengthToDisplay;
      }
      if (data.settings.maxIdleTime) {
        currentSettings.maxIdleTime = data.settings.maxIdleTime;
      }
      if (data.settings.overlayHideTimeout) {
        currentSettings.overlayHideTimeout = data.settings.overlayHideTimeout;
      }
      console.log('Loaded settings:', currentSettings);
      
      // Initialize buffer with empty lines based on numOfLines setting
      initializeBuffer();
    }
  });
}

function initializeBuffer() {
  // Initialize buffer with the correct number of empty lines
  textBuffer = new Array(currentSettings.numOfLines).fill('');
}

function createOverlay() {
  // Check if overlay already exists
  if (document.getElementById('whisper-transcription-overlay')) {
    console.log('Overlay already exists, reusing existing element');
    overlay = document.getElementById('whisper-transcription-overlay');
    textContainer = document.getElementById('whisper-transcription-text');
    return;
  }
  
  // Create main overlay container
  overlay = document.createElement('div');
  overlay.id = 'whisper-transcription-overlay';
  overlay.style.cssText = `
    position: fixed;
    left: 50%;
    transform: translateX(-50%);
    width: auto;     /* Changed from fixed 40% to auto */
    max-width: 80%;  /* Added max-width to prevent too wide overlay */
    background-color: rgba(0, 0, 0, 0.7);
    color: white;
    z-index: 10000;
    padding: 15px;
    border-radius: 8px;
    font-family: Arial, sans-serif;
    display: none;  /* Initially hidden but will be changed to flex when shown */
    flex-direction: column;
    align-items: center;  /* Center text horizontally */
    justify-content: flex-start;  /* Align from top for proper line display */
    overflow: hidden;
    opacity: 0.8;
    cursor: move;
    height: auto;  /* Allow height to adjust based on content */
    min-height: 20px;
    min-width: 200px; /* Added min-width to ensure it's never too small */
    user-select: none;
    transition: max-width 0.3s ease;  /* Smooth transition for width changes */
  `;
  
  // Add drag event listeners
  overlay.addEventListener('mousedown', startDragging);
  document.addEventListener('mousemove', handleDrag);
  document.addEventListener('mouseup', stopDragging);
  
  // Add window resize listener
  window.addEventListener('resize', handleWindowResize);

  // Create container for transcription text
  textContainer = document.createElement('div');
  textContainer.id = 'whisper-transcription-text';
  textContainer.style.cssText = `
    width: 100%;
    font-size: 18px;
    line-height: 1.4;
    text-align: center;  /* Center text */
    display: flex;
    flex-direction: column;
  `;
  
  // Initialize textBuffer and create line elements
  initializeBuffer();
  updateTextDisplay();
  
  // Append container to overlay
  overlay.appendChild(textContainer);
  document.body.appendChild(overlay);
}

// Add new drag handling functions
function startDragging(e) {
  isDragging = true;
  const rect = overlay.getBoundingClientRect();
  
  // Store the initial dimensions
  const width = rect.width;
  
  // Remove transform and set absolute positioning
  overlay.style.transform = 'none';
  overlay.style.bottom = 'auto';
  overlay.style.left = rect.left + 'px';
  overlay.style.top = rect.top + 'px';
  overlay.style.width = width + 'px';
  
  dragOffset = {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  };
  
  // Prevent text selection during drag
  e.preventDefault();
}

function handleDrag(e) {
  if (!isDragging) return;
  
  const x = e.clientX - dragOffset.x;
  const y = e.clientY - dragOffset.y;
  
  // Ensure the overlay stays within viewport bounds
  const rect = overlay.getBoundingClientRect();
  const maxX = window.innerWidth - rect.width;
  const maxY = window.innerHeight - rect.height;
  
  overlay.style.left = `${Math.min(Math.max(0, x), maxX)}px`;
  overlay.style.top = `${Math.min(Math.max(0, y), maxY)}px`;
}

function stopDragging() {
  if (isDragging) {
    // Save the current position for future use
    overlayPosition.left = overlay.style.left;
    overlayPosition.top = overlay.style.top;
  }
  isDragging = false;
}

function updateTranscriptionText(message) {
  if (!textContainer) {
    console.error('Text container not found, recreating overlay');
    createOverlay();
  }
  
  const now = Date.now();
  
  // Reset timer if it exists
  if (updateTimer) {
    clearTimeout(updateTimer);
  }

  let text = '';
  if (message.text) {
    text = message.text.trim();
    
    // If this is a translation, format it differently
    if (message.isTranslation) {
      currentText = text;
      // currentText += (currentText ? ' ' : '') + text;
    } else {
      // Append new text to our current accumulating text
      currentText += (currentText ? ' ' : '') + text;
    }
  }

  // Check if we should update the display based on conditions
  const shouldUpdateDisplay = 
    // message.isFinal || // Always update for translations or final segments
    currentText.length >= currentSettings.minLengthToDisplay || 
    (now - lastUpdateTime > currentSettings.maxIdleTime * 1000 && currentText.trim() !== '');
  
  if (shouldUpdateDisplay) {
    // Push to buffer and shift out oldest item
    if (currentText.trim()) {
      textBuffer.push(currentText.trim());
      textBuffer.shift();
    }
    
    // Update the display
    updateTextDisplay();
    
    // Reset the current text accumulation if not a translation
    if (!message.isTranslation) {
      currentText = '';
    }
    lastUpdateTime = now;
  } else {
    // Set a timer to check again after max idle time
    updateTimer = setTimeout(() => {
      // If we still have accumulated text, update the display
      if (currentText.trim()) {
        textBuffer.push(currentText.trim());
        textBuffer.shift();
        updateTextDisplay();
        currentText = '';
      }
    }, currentSettings.maxIdleTime * 1000);
  }
  
  lastUpdateTime = now;
  
  // Show overlay and reset hide timer
  showOverlay();
}

function updateTextDisplay() {
  // Clear the existing content
  textContainer.innerHTML = '';
  
  // Create and add elements for each line in the buffer
  textBuffer.forEach((line, index) => {
    const lineElement = document.createElement('div');
    lineElement.id = `transcription-line-${index}`;
    lineElement.textContent = line;
    lineElement.style.cssText = `
      width: 100%;
      margin-bottom: 6px;
      color: ${index < textBuffer.length - 1 ? '#cccccc' : 'white'};
      transition: opacity 0.3s ease;
    `;
    
    textContainer.appendChild(lineElement);
  });
}

function showOverlay() {
  if (!overlay) {
    console.error('Overlay element not found, recreating overlay');
    createOverlay();
  }
  
  if (overlay) {
    // Only apply initial positioning when first displayed
    if (overlay.style.display === 'none') {
      if (overlayPosition.left === '50%') {
        // Initial centered position
        overlay.style.left = '50%';
        overlay.style.top = '80%';
        overlay.style.transform = 'translateX(-50%)';
      } else {
        // Use saved position from dragging
        overlay.style.transform = 'none';
        overlay.style.bottom = 'auto';
        overlay.style.left = overlayPosition.left;
        overlay.style.top = overlayPosition.top;
      }
    }
    
    overlay.style.display = 'flex';
    isVisible = true;
    console.log('Overlay should now be visible');
    
    // Reset hide timer whenever we show the overlay
    resetHideTimer();
  } else {
    console.error('Failed to create or find overlay element');
  }
}

function hideOverlay() {
  if (!overlay) return;
  overlay.style.display = 'none';
  isVisible = false;
  
  // Don't clear the text buffer when hiding overlay
  // Text should persist between hide/show events
  // textBuffer = [];
  // updateTextDisplay();
}

function resetHideTimer() {
  // Clear existing timer if any
  if (hideTimer) {
    clearTimeout(hideTimer);
  }
  
  // Set new timer
  hideTimer = setTimeout(() => {
    if (isVisible) {
      hideOverlay();
    }
  }, currentSettings.overlayHideTimeout * 1000);
}

function applySettings() {
  if (!overlay || !textContainer) return;
  
  // Apply text size
  let fontSize = '18px';
  switch (currentSettings.textSize) {
    case 'small':
      fontSize = '14px';
      break;
    case 'large':
      fontSize = '22px';
      break;
    default:
      fontSize = '18px';
  }
  
  textContainer.style.fontSize = fontSize;
  
  // Apply opacity
  overlay.style.opacity = currentSettings.overlayOpacity || 0.8;
  
  // Update buffer size if number of lines changed
  if (textBuffer.length !== currentSettings.numOfLines) {
    // Create a new buffer with the new size
    const newBuffer = new Array(currentSettings.numOfLines).fill('');
    
    // Copy existing items, prioritizing the most recent ones
    const startIdx = Math.max(0, textBuffer.length - currentSettings.numOfLines);
    for (let i = 0; i < Math.min(textBuffer.length, currentSettings.numOfLines); i++) {
      newBuffer[newBuffer.length - i - 1] = textBuffer[textBuffer.length - i - 1] || '';
    }
    
    textBuffer = newBuffer;
    updateTextDisplay();
  }
}

// Add window resize handler function
function handleWindowResize() {
  if (!overlay) return;
  
  // If the overlay is using absolute positioning (was dragged)
  if (overlay.style.transform !== 'translateX(-50%)') {
    // Get current overlay dimensions
    const rect = overlay.getBoundingClientRect();
    
    // Ensure it stays within viewport bounds
    const maxX = window.innerWidth - rect.width;
    const maxY = window.innerHeight - rect.height;
    
    // Update position if needed
    if (parseFloat(overlay.style.left) > maxX) {
      overlay.style.left = `${maxX}px`;
    }
    
    if (parseFloat(overlay.style.top) > maxY) {
      overlay.style.top = `${maxY}px`;
    }
  } else {
    // For centered overlay, just ensure max-width is appropriate
    // This happens automatically via CSS, but you could add custom logic here
  }
  
  // Update stored position
  overlayPosition.left = overlay.style.left;
  overlayPosition.top = overlay.style.top;
}

// Add this function to handle cleanup when extension is deactivated
function cleanup() {
  // Remove event listeners
  if (overlay) {
    overlay.removeEventListener('mousedown', startDragging);
  }
  document.removeEventListener('mousemove', handleDrag);
  document.removeEventListener('mouseup', stopDragging);
  window.removeEventListener('resize', handleWindowResize);
  
  // Remove overlay from DOM if it exists
  if (overlay && overlay.parentNode) {
    overlay.parentNode.removeChild(overlay);
  }
  
  // Reset variables
  overlay = null;
  textContainer = null;
  isVisible = false;
}
