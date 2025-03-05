// Global variables
let overlay = null;
let textContainer = null;
let translationContainer = null;
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
    if (message.action === 'updateTranscription') {
      updateTranscriptionText(message.text, message.isFinal, message.translation);
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
    display: flex;
    flex-direction: column;
    overflow: hidden;
    opacity: 0.8;
    transition: opacity 0.3s ease;
    pointer-events: none;
    display: none;
  `;
  
  // Create container for transcription text
  textContainer = document.createElement('div');
  textContainer.id = 'whisper-transcription-text';
  textContainer.style.cssText = `
    margin-bottom: 10px;
    overflow-y: auto;
    max-height: 100%;
    font-size: 18px;
    line-height: 1.4;
  `;
  
  // Create container for translation text (if available)
  translationContainer = document.createElement('div');
  translationContainer.id = 'whisper-translation-text';
  translationContainer.style.cssText = `
    font-style: italic;
    border-top: 1px solid rgba(255, 255, 255, 0.3);
    padding-top: 10px;
    margin-top: 10px;
    overflow-y: auto;
    max-height: 100%;
    font-size: 16px;
    color: #ccccff;
    display: none;
  `;
  
  // Append elements to the document
  overlay.appendChild(textContainer);
  overlay.appendChild(translationContainer);
  document.body.appendChild(overlay);
}

function updateTranscriptionText(text, isFinal, translation) {
  if (!textContainer) return;
  
  // Update main transcription text
  textContainer.textContent = text || 'Listening...';
  
  // If there's translation text, show the translation container and update it
  if (translation) {
    translationContainer.style.display = 'block';
    translationContainer.textContent = translation;
  } else {
    translationContainer.style.display = 'none';
  }
  
  // Scroll to the bottom if content overflows
  textContainer.scrollTop = textContainer.scrollHeight;
  if (translation) {
    translationContainer.scrollTop = translationContainer.scrollHeight;
  }
}

function showOverlay() {
  if (!overlay) return;
  overlay.style.display = 'block';
  isVisible = true;
}

function hideOverlay() {
  if (!overlay) return;
  overlay.style.display = 'none';
  isVisible = false;
}

function applySettings() {
  if (!overlay || !textContainer || !translationContainer) return;
  
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
  translationContainer.style.fontSize = (parseInt(fontSize) - 2) + 'px';
  
  // Apply opacity
  overlay.style.opacity = currentSettings.overlayOpacity || 0.8;
}