let mediaStream = null;
let audioContext = null;
let websocket = null;

// Listen for messages from the service worker
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'startCapture') {
    startCapture(message.settings, message.tabId)
      .then(() => sendResponse({ status: 'started' }))
      .catch(error => sendResponse({ status: 'error', message: error.message }));
    return true; // Required for async sendResponse
  } 
  else if (message.action === 'stopCapture') {
    stopCapture()
      .then(() => sendResponse({ status: 'stopped' }))
      .catch(error => sendResponse({ status: 'error', message: error.message }));
    return true;
  }
});

async function startCapture(settings, tabId) {
  try {
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
    
    // Store the stream
    mediaStream = stream;
    
    // Notify the service worker that capture started successfully
    chrome.runtime.sendMessage({
      action: 'captureStarted',
      stream: true,  // We can't transfer the actual stream, so we just indicate success
      tabId: tabId,
      settings: settings
    });
    
    // Set up a listener for the stream ending
    stream.getAudioTracks()[0].onended = () => {
      chrome.runtime.sendMessage({ action: 'streamEnded' });
    };
    
    // Process audio with AudioContext and send it to background via messages
    await processAudio(stream, settings);
    
  } catch (error) {
    console.error('Error in startCapture:', error);
    chrome.runtime.sendMessage({ 
      action: 'captureError', 
      error: error.message 
    });
    throw error;
  }
}

async function processAudio(stream, settings) {
  // Create audio context
  audioContext = new AudioContext();
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  
  // Import the processing function from audioProcessor.js
  const { processAudioChunk } = await import('./audioProcessor.js');
  
  // Connect source to processor
  source.connect(processor);
  processor.connect(audioContext.destination);
  
  // Define processing function
  processor.onaudioprocess = (e) => {
    const audioData = e.inputBuffer.getChannelData(0);
    // Convert and send audio data to background
    const processedData = processAudioChunk(audioData, audioContext.sampleRate);
    chrome.runtime.sendMessage({
      action: 'audioChunk',
      audioData: Array.from(processedData),  // Convert to array for sending
      settings: settings
    });
  };
}

async function stopCapture() {
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
  
  // Notify background
  chrome.runtime.sendMessage({ action: 'captureStopped' });
}

// Keep alive
setInterval(() => {
  if (mediaStream) {
    chrome.runtime.sendMessage({ action: 'keepAlive' });
  }
}, 25000);