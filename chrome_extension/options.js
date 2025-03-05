document.addEventListener('DOMContentLoaded', () => {
  // Load saved settings
  loadSavedSettings();
  
  // Set up event listeners for settings changes
  document.getElementById('serverUrl').addEventListener('change', saveSettings);
  document.getElementById('textSize').addEventListener('change', saveSettings);
  document.getElementById('overlayOpacity').addEventListener('input', saveSettings);
  document.getElementById('shortChunkThreshold').addEventListener('change', saveSettings);
  document.getElementById('longChunkThreshold').addEventListener('change', saveSettings);
  document.getElementById('maxLineLength').addEventListener('change', saveSettings);
  document.getElementById('numOfLines').addEventListener('change', saveSettings);
  document.getElementById('minLengthToDisplay').addEventListener('change', saveSettings);
  document.getElementById('maxIdleTime').addEventListener('change', saveSettings);
  
  // Set up test button
  document.getElementById('testButton').addEventListener('click', testConnection);
});

function loadSavedSettings() {
  chrome.storage.sync.get(['serverUrl', 'settings'], (data) => {
    // Server URL
    if (data.serverUrl) {
      document.getElementById('serverUrl').value = data.serverUrl;
    }
    
    // Other settings
    if (data.settings) {
      if (data.settings.textSize) {
        document.getElementById('textSize').value = data.settings.textSize;
      }
      
      if (data.settings.overlayOpacity !== undefined) {
        document.getElementById('overlayOpacity').value = data.settings.overlayOpacity * 100;
        document.getElementById('opacityValue').textContent = Math.round(data.settings.overlayOpacity * 100) + '%';
      }
      
      if (data.settings.shortChunkThreshold !== undefined) {
        document.getElementById('shortChunkThreshold').value = data.settings.shortChunkThreshold;
      }
      
      if (data.settings.longChunkThreshold !== undefined) {
        document.getElementById('longChunkThreshold').value = data.settings.longChunkThreshold;
      }
      
      if (data.settings.maxLineLength !== undefined) {
        document.getElementById('maxLineLength').value = data.settings.maxLineLength;
      }
      
      if (data.settings.numOfLines !== undefined) {
        document.getElementById('numOfLines').value = data.settings.numOfLines;
      }
      
      if (data.settings.minLengthToDisplay !== undefined) {
        document.getElementById('minLengthToDisplay').value = data.settings.minLengthToDisplay;
      }
      
      if (data.settings.maxIdleTime !== undefined) {
        document.getElementById('maxIdleTime').value = data.settings.maxIdleTime;
      }
    }
    
    // Update opacity display
    document.getElementById('overlayOpacity').addEventListener('input', function() {
      document.getElementById('opacityValue').textContent = this.value + '%';
    });
  });
}

function saveSettings() {
  // Save server URL
  const serverUrl = document.getElementById('serverUrl').value;
  chrome.storage.sync.set({ serverUrl });
  
  // Save other settings
  const settings = {
    textSize: document.getElementById('textSize').value,
    overlayOpacity: document.getElementById('overlayOpacity').value / 100,
    shortChunkThreshold: parseInt(document.getElementById('shortChunkThreshold').value),
    longChunkThreshold: parseInt(document.getElementById('longChunkThreshold').value),
    maxLineLength: parseInt(document.getElementById('maxLineLength').value),
    numOfLines: parseInt(document.getElementById('numOfLines').value),
    minLengthToDisplay: parseInt(document.getElementById('minLengthToDisplay').value),
    maxIdleTime: parseFloat(document.getElementById('maxIdleTime').value)
  };
  
  chrome.storage.sync.set({ settings }, () => {
    console.log('Settings saved:', settings);
    
    // Show saved message
    const status = document.getElementById('status');
    status.textContent = 'Settings saved!';
    setTimeout(() => {
      status.textContent = '';
    }, 2000);
    
    // Send message to any open tabs to update settings
    chrome.tabs.query({}, (tabs) => {
      tabs.forEach(tab => {
        chrome.tabs.sendMessage(tab.id, {
          action: 'settingsUpdated',
          settings: settings
        }).catch(err => console.log('Error sending settings update to tab:', err));
      });
    });
  });
}

function testConnection() {
  const serverUrl = document.getElementById('serverUrl').value;
  const testUrl = serverUrl.replace(/\/$/, '') + '/health';
  const statusElem = document.getElementById('connectionStatus');
  
  statusElem.textContent = 'Testing connection...';
  statusElem.style.color = 'blue';
  
  fetch(testUrl)
    .then(response => {
      if (response.ok) {
        return response.json();
      }
      throw new Error(`HTTP error! Status: ${response.status}`);
    })
    .then(data => {
      statusElem.textContent = 'Connection successful!';
      statusElem.style.color = 'green';
      console.log('Server response:', data);
    })
    .catch(error => {
      statusElem.textContent = `Connection failed: ${error.message}`;
      statusElem.style.color = 'red';
      console.error('Connection test error:', error);
    });
}