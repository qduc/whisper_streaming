import { WebSocketClient } from './websocketClient.js';

// Default connection settings
let defaultSettings = {
  serverUrl: 'ws://localhost:43007',
  textSize: 'medium',
  overlayOpacity: 0.8
};

// Global variables
let websocket = null;
let isTranscribing = false;
let currentTabId = null;

// Initialize with stored settings or defaults
chrome.storage.sync.get('settings', (data) => {
  if (data.settings) {
    defaultSettings = { ...defaultSettings, ...data.settings };
  }
});

// Check if offscreen document exists
async function hasOffscreenDocument() {
  try {
    const existingContexts = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT'],
      documentUrls: ['offscreen.html']
    });
    return existingContexts.length > 0;
  } catch (error) {
    console.error('Error checking for offscreen document:', error);
    return false;
  }
}

// Create offscreen document if needed
async function setupOffscreenDocument() {
  try {
    // First check if document already exists
    const exists = await hasOffscreenDocument();
    
    // If it exists, don't create a new one
    if (exists) {
      console.log('Offscreen document already exists, reusing it');
      return;
    }
    
    // Wait to ensure any pending close operations have completed
    await new Promise(resolve => setTimeout(resolve, 200));
    
    // Create a new document
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Needed to access tab capture API'
    });
    
    console.log('Offscreen document created successfully');
  } catch (error) {
    console.error('Error setting up offscreen document:', error);
    
    // If the error is about duplicate documents, try to close and retry once
    if (error.message && error.message.includes('Only a single offscreen document may be created')) {
      console.log('Attempting to recover by closing existing document');
      try {
        await chrome.offscreen.closeDocument();
        // Wait before trying again
        await new Promise(resolve => setTimeout(resolve, 300));
        await chrome.offscreen.createDocument({
          url: 'offscreen.html',
          reasons: ['USER_MEDIA'],
          justification: 'Needed to access tab capture API'
        });
        console.log('Successfully recovered and created offscreen document');
      } catch (retryError) {
        console.error('Recovery failed:', retryError);
        throw retryError;
      }
    } else {
      throw error;
    }
  }
}

// Listen for messages from popup or content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'startTranscription') {
    startTranscription(message.settings || defaultSettings)
      .then(() => sendResponse({ status: 'started' }))
      .catch(error => sendResponse({ status: 'error', message: error.message }));
    return true; // Required for async sendResponse
  } 
  else if (message.action === 'stopTranscription') {
    stopTranscription()
      .then(() => sendResponse({ status: 'stopped' }))
      .catch(error => sendResponse({ status: 'error', message: error.message }));
    return true;
  }
  else if (message.action === 'getStatus') {
    sendResponse({ isTranscribing });
    return true;
  }
  // Handle messages from offscreen document
  else if (message.action === 'captureStarted') {
    handleCaptureStarted(message.tabId, message.settings);
  }
  else if (message.action === 'audioChunk') {
    handleAudioChunk(message.audioData);
  }
  else if (message.action === 'captureStopped' || message.action === 'streamEnded') {
    if (isTranscribing) {
      stopTranscription().catch(console.error);
    }
  }
});

// Start the transcription process
async function startTranscription(settings) {
  if (isTranscribing) {
    await stopTranscription();
    // Add a small delay after stopping to ensure cleanup is complete
    await new Promise(resolve => setTimeout(resolve, 200));
  }

  try {
    // Get active tab
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs.length === 0) {
      throw new Error('No active tab found');
    }
    
    currentTabId = tabs[0].id;
    
    // Create WebSocket connection
    websocket = new WebSocketClient(settings.serverUrl);
    await websocket.connect();
    
    // Set up message handler for transcriptions
    websocket.onMessage((data) => {
      // Forward transcription to content script in the active tab
      chrome.tabs.sendMessage(currentTabId, {
        action: 'updateTranscription',
        ...data  // This spreads all the JSON message fields
      });
    });
    
    // Setup offscreen document to handle tab capture
    await setupOffscreenDocument();
    
    // Chrome 116+: Get media stream ID in the service worker
    const streamId = await chrome.tabCapture.getMediaStreamId({ 
      targetTabId: currentTabId 
    });
    
    // Update settings with the stream ID to pass to offscreen document
    const settingsWithStream = {
      ...settings,
      streamId: streamId
    };
    
    // Request the offscreen document to start capturing with the stream ID
    chrome.runtime.sendMessage({
      action: 'startCapture',
      tabId: currentTabId,
      settings: settingsWithStream
    });
    
    // Notify content script to show overlay
    chrome.tabs.sendMessage(currentTabId, {
      action: 'showOverlay',
      settings: settings
    });
    
  } catch (error) {
    console.error('Error starting transcription:', error);
    throw error;
  }
}

// Handle successful capture start
function handleCaptureStarted(tabId, settings) {
  isTranscribing = true;
  
  // Update popup if it's open
  chrome.runtime.sendMessage({
    action: 'statusUpdate',
    status: 'listening'
  }).catch(() => {
    // Popup might be closed, ignore error
  });
}

// Handle audio chunks from offscreen document
function handleAudioChunk(audioData) {
  if (!isTranscribing || !websocket) return;
  
  // Convert array back to Int16Array
  const int16Data = new Int16Array(audioData);
  
  // Send to WebSocket
  websocket.sendAudio(int16Data);
}

// Stop the transcription process
async function stopTranscription() {
  isTranscribing = false;
  
  // Tell offscreen document to stop capturing and wait for response
  try {
    const response = await chrome.runtime.sendMessage({
      action: 'stopCapture'
    });
    
    // Wait a small delay to ensure offscreen cleanup is completed
    await new Promise(resolve => setTimeout(resolve, 100));
  } catch (error) {
    console.error('Error stopping capture:', error);
    // Continue with cleanup even if there's an error
  }
  
  // Stop WebSocket
  if (websocket) {
    await websocket.disconnect();
    websocket = null;
  }
  
  // Hide overlay in content script
  if (currentTabId) {
    chrome.tabs.sendMessage(currentTabId, {
      action: 'hideOverlay'
    }).catch(() => {
      // Tab might be closed, ignore error
    });
  }
  
  // Update popup if it's open
  chrome.runtime.sendMessage({
    action: 'statusUpdate',
    status: 'disconnected'
  }).catch(() => {
    // Popup might be closed, ignore error
  });
  
  // Close offscreen document if it exists
  try {
    const hasOffscreen = await hasOffscreenDocument();
    if (hasOffscreen) {
      await chrome.offscreen.closeDocument();
    }
  } catch (error) {
    console.error('Error closing offscreen document:', error);
  }
}

// Clean up when tab is closed
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === currentTabId && isTranscribing) {
    stopTranscription();
  }
});