// Global variables
let overlay = null;
let textContainer = null;
let isVisible = false;
let currentSettings = {
  textSize: 'medium',
  overlayOpacity: 0.8
};

// Initialize when the content script loads
initialize();

function initialize() {
  // Create overlay elements but keep them hidden initially
  createOverlay();
  
  // Listen for messages from background script
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('Received message:', message);
    
    if (message.action === 'updateTranscription') {
      updateTranscriptionText(message.text, message.isFinal);
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
    left: 10%;
    width: 80%;
    max-height: 30%;
    background-color: rgba(0, 0, 0, 0.7);
    color: white;
    z-index: 10000;
    padding: 15px;
    border-radius: 8px;
    font-family: Arial, sans-serif;
    display: none;  /* Initially hidden but will be changed to flex when shown */
    flex-direction: column;
    overflow: hidden;
    opacity: 0.8;
    transition: opacity 0.3s ease;
    pointer-events: none;
  `;
  
  // Create container for transcription text
  textContainer = document.createElement('div');
  textContainer.id = 'whisper-transcription-text';
  textContainer.style.cssText = `
    overflow-y: auto;
    max-height: 100%;
    font-size: 18px;
    line-height: 1.4;
  `;
  
  // Append elements to the document
  overlay.appendChild(textContainer);
  document.body.appendChild(overlay);
}

function updateTranscriptionText(text, isFinal) {
  if (!textContainer) return;
  
  // Update main transcription text
  textContainer.textContent = text || 'Listening...';
  
  // Scroll to the bottom if content overflows
  textContainer.scrollTop = textContainer.scrollHeight;
  
  // Ensure overlay is visible whenever we get transcription updates
  if (!isVisible) {
    showOverlay();
  }
}

function showOverlay() {
  if (!overlay) return;
  overlay.style.display = 'flex';  // Change to flex instead of block
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
  console.log('Overlay visible state:', isVisible);
  console.log('Overlay display style:', overlay.style.display);
}