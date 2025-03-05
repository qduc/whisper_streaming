// Global variables
let overlay = null;
let textContainer = null;
let isVisible = false;
let currentLine = '';
let previousLine = '';
let currentSettings = {
  textSize: 'medium',
  overlayOpacity: 0.8
};
let lineChangeTimeout = null;

// Initialize when the content script loads
initialize();

function initialize() {
  // Create overlay elements but keep them hidden initially
  createOverlay();
  
  // Listen for messages from background script
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('Received message:', message);
    
    if (message.action === 'updateTranscription') {
      updateTranscriptionText(message.text);
    }
    else if (message.action === 'showOverlay') {
      if (message.settings) {
        currentSettings = message.settings;
        applySettings();
      }
      showOverlay();
    }
    else if (message.action === 'hideOverlay') {
      hideOverlay();
    }
  });
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
    width: 60%;  /* Wider to accommodate more text */
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
    min-height: 80px;  /* Ensure height for two lines */
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
  
  // Create previous and current line elements
  const previousLineElement = document.createElement('div');
  previousLineElement.id = 'previous-transcription-line';
  previousLineElement.style.cssText = `
    width: 100%;
    color: #cccccc;  /* Slightly faded color for previous line */
    margin-bottom: 8px;
    transition: opacity 0.3s ease;
  `;
  
  const currentLineElement = document.createElement('div');
  currentLineElement.id = 'current-transcription-line';
  currentLineElement.style.cssText = `
    width: 100%;
  `;
  
  // Append elements to the container
  textContainer.appendChild(previousLineElement);
  textContainer.appendChild(currentLineElement);
  
  // Append container to overlay
  overlay.appendChild(textContainer);
  document.body.appendChild(overlay);
}

function updateTranscriptionText(text) {
  if (!textContainer) return;
  
  const previousLineElement = document.getElementById('previous-transcription-line');
  const currentLineElement = document.getElementById('current-transcription-line');
  
  if (!previousLineElement || !currentLineElement) return;
  
  if (text === null || text === undefined) {
    // Reset if no text is provided
    currentLine = 'Listening...';
    currentLineElement.textContent = currentLine;
    return;
  }
  
  // Clear any previous timeout
  if (lineChangeTimeout) {
    clearTimeout(lineChangeTimeout);
  }
  
  // Handle text chunks intelligently
  if (text.length < 15 && currentLine.length + text.length < 100) {
    // If the new chunk is very short, append it to current line
    currentLine = (currentLine + ' ' + text).trim();
  } else if (text.length > 80 || text.endsWith('.') || text.endsWith('?') || text.endsWith('!')) {
    // If we have a substantial amount of text or it ends with sentence-ending punctuation,
    // consider it a new complete thought/sentence
    
    // Move current line to previous
    previousLine = currentLine.trim();
    previousLineElement.textContent = previousLine;
    
    // Set the new text as current line
    currentLine = text.trim();
    
    // Set a timeout to clear the previous line after a delay if no new text comes in
    lineChangeTimeout = setTimeout(() => {
      if (previousLineElement && previousLineElement.textContent === previousLine) {
        previousLine = '';
        previousLineElement.textContent = '';
      }
    }, 5000); // Clear previous line after 5 seconds if no new text
  } else {
    // For other updates, replace the current line
    currentLine = text.trim();
  }
  
  currentLineElement.textContent = currentLine;
  
  // Ensure overlay is visible whenever we get transcription updates
  if (!isVisible) {
    showOverlay();
  }
}

function showOverlay() {
  if (!overlay) return;
  overlay.style.display = 'flex';
  isVisible = true;
}

function hideOverlay() {
  if (!overlay) return;
  overlay.style.display = 'none';
  isVisible = false;
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
}

function testOverlay() {
  console.log('Testing overlay visibility...');
  showOverlay();
  updateTranscriptionText('This is a test of the whisper overlay system.');
  setTimeout(() => {
    updateTranscriptionText('This is a second line of text.');
  }, 2000);
  console.log('Overlay visible state:', isVisible);
  console.log('Overlay display style:', overlay.style.display);
}