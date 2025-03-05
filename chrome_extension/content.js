// Global variables
let overlay = null;
let textContainer = null;
let isVisible = false;
let textBuffer = [];
let currentText = '';
let lastUpdateTime = 0;
let updateTimer = null;
let currentSettings = {
  textSize: 'medium',
  overlayOpacity: 0.8,
  shortChunkThreshold: 15,   // Legacy setting
  longChunkThreshold: 80,    // Legacy setting
  maxLineLength: 100,        // Legacy setting
  numOfLines: 3,             // Default number of lines in the buffer
  minLengthToDisplay: 30,    // Minimum text length to display
  maxIdleTime: 1.5           // Maximum idle time in seconds before displaying buffer
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
        updateTranscriptionText(message.text);
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
  // Create main overlay container
  overlay = document.createElement('div');
  overlay.id = 'whisper-transcription-overlay';
  overlay.style.cssText = `
    position: fixed;
    bottom: 10%;
    left: 50%;
    transform: translateX(-50%);
    min-width: 40%;  /* Wider to accommodate more text */
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
    transition: opacity 0.3s ease;
    pointer-events: none;
    min-height: 80px;  /* Ensure height for multiple lines */
  `;
  
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

function updateTranscriptionText(text) {
  if (!textContainer) {
    console.error('Text container not found, recreating overlay');
    createOverlay();
  }
  
  const now = Date.now();
  
  // Reset timer if it exists
  if (updateTimer) {
    clearTimeout(updateTimer);
  }
  
  if (text === null || text === undefined || text.trim() === '') {
    // If no text is provided, just handle as idle time passing
    text = '';
  } else {
    text = text.trim();
    // Append new text to our current accumulating text
    currentText += (currentText ? ' ' : '') + text;
  }
  
  // Check if we should update the display based on conditions
  const shouldUpdateDisplay = 
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
    
    // Reset the current text accumulation
    currentText = '';
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
  
  // Ensure overlay is visible whenever we get transcription updates
  if (!isVisible) {
    showOverlay();
  }
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
    overlay.style.display = 'flex';
    isVisible = true;
    console.log('Overlay should now be visible');
  } else {
    console.error('Failed to create or find overlay element');
  }
}

function hideOverlay() {
  if (!overlay) return;
  overlay.style.display = 'none';
  isVisible = false;
  textBuffer = [];
  updateTextDisplay();
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
