document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const actionButton = document.getElementById('action-button');
  const statusElement = document.getElementById('status');
  const errorElement = document.getElementById('error-message');
  const serverUrlInput = document.getElementById('server-url');
  const textSizeSelect = document.getElementById('text-size');
  const opacityInput = document.getElementById('overlay-opacity');
  
  let isTranscribing = false;
  
  // Load saved settings
  chrome.storage.sync.get('settings', (data) => {
    if (data.settings) {
      serverUrlInput.value = data.settings.serverUrl || 'ws://localhost:43007';
      textSizeSelect.value = data.settings.textSize || 'medium';
      opacityInput.value = data.settings.overlayOpacity || 0.8;
    }
  });
  
  // Check current transcription status
  chrome.runtime.sendMessage({ action: 'getStatus' }, (response) => {
    updateUIState(response.isTranscribing);
  });
  
  // Event listener for button click
  actionButton.addEventListener('click', async () => {
    try {
      hideError();
      
      if (!isTranscribing) {
        // Start transcription
        await startTranscription();
      } else {
        // Stop transcription
        await stopTranscription();
      }
    } catch (error) {
      showError(error.message);
    }
  });
  
  // Listen for status updates from background script
  chrome.runtime.onMessage.addListener((message) => {
    if (message.action === 'statusUpdate') {
      updateUIState(message.status === 'listening');
    }
  });
  
  // Start transcription
  async function startTranscription() {
    // Save settings
    const settings = {
      serverUrl: serverUrlInput.value,
      textSize: textSizeSelect.value,
      overlayOpacity: parseFloat(opacityInput.value)
    };
    
    chrome.storage.sync.set({ settings });
    
    // Send start message to background script
    const response = await chrome.runtime.sendMessage({
      action: 'startTranscription',
      settings
    });
    
    if (response.status === 'error') {
      throw new Error(response.message);
    }
    
    updateUIState(true);
  }
  
  // Stop transcription
  async function stopTranscription() {
    // Send stop message to background script
    const response = await chrome.runtime.sendMessage({
      action: 'stopTranscription'
    });
    
    if (response.status === 'error') {
      throw new Error(response.message);
    }
    
    updateUIState(false);
  }
  
  // Update UI based on transcription state
  function updateUIState(transcribing) {
    isTranscribing = transcribing;
    
    if (transcribing) {
      actionButton.textContent = 'Stop Transcription';
      actionButton.classList.add('stop');
      statusElement.textContent = 'Listening...';
      statusElement.className = 'status listening';
    } else {
      actionButton.textContent = 'Start Transcription';
      actionButton.classList.remove('stop');
      statusElement.textContent = 'Disconnected';
      statusElement.className = 'status disconnected';
    }
  }
  
  // Display error message
  function showError(message) {
    errorElement.textContent = message;
    errorElement.style.display = 'block';
  }
  
  // Hide error message
  function hideError() {
    errorElement.style.display = 'none';
  }
});