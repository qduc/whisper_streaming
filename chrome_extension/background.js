import { processAudio } from './audioProcessor.js';
import { WebSocketClient } from './websocketClient.js';

// Default connection settings
let defaultSettings = {
  serverUrl: 'ws://localhost:43007',
  textSize: 'medium',
  overlayOpacity: 0.8
};

// Global variables
let mediaStream = null;
let audioContext = null;
let websocket = null;
let isTranscribing = false;
let currentTabId = null;

// Initialize with stored settings or defaults
chrome.storage.sync.get('settings', (data) => {
  if (data.settings) {
    defaultSettings = { ...defaultSettings, ...data.settings };
  }
});

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
});

// Start the transcription process
async function startTranscription(settings) {
  if (isTranscribing) {
    await stopTranscription();
  }

  try {
    // Get active tab
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs.length === 0) {
      throw new Error('No active tab found');
    }
    
    currentTabId = tabs[0].id;
    
    // Request tab audio stream
    const stream = await chrome.tabCapture.capture({
      audio: true,
      video: false,
      audioConstraints: {
        mandatory: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      }
    });
    
    if (!stream) {
      throw new Error('Failed to capture tab audio');
    }
    
    mediaStream = stream;
    
    // Create WebSocket connection
    websocket = new WebSocketClient(settings.serverUrl);
    
    await websocket.connect();
    
    // Setup audio context and processing
    audioContext = new AudioContext();
    await processAudio(mediaStream, audioContext, websocket);
    
    // Set up message handler for transcriptions
    websocket.onMessage((data) => {
      // Forward transcription to content script in the active tab
      chrome.tabs.sendMessage(currentTabId, {
        action: 'updateTranscription',
        text: data.text,
        isFinal: data.isFinal,
        translation: data.translation
      });
    });
    
    // Notify content script to show overlay
    chrome.tabs.sendMessage(currentTabId, {
      action: 'showOverlay',
      settings: settings
    });
    
    isTranscribing = true;
    
    // Update popup if it's open
    chrome.runtime.sendMessage({
      action: 'statusUpdate',
      status: 'listening'
    }).catch(() => {
      // Popup might be closed, ignore error
    });
    
  } catch (error) {
    console.error('Error starting transcription:', error);
    isTranscribing = false;
    throw error;
  }
}

// Stop the transcription process
async function stopTranscription() {
  isTranscribing = false;
  
  // Stop WebSocket
  if (websocket) {
    await websocket.disconnect();
    websocket = null;
  }
  
  // Stop media stream
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }
  
  // Close audio context
  if (audioContext) {
    await audioContext.close();
    audioContext = null;
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
}

// Clean up when tab is closed
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === currentTabId && isTranscribing) {
    stopTranscription();
  }
});