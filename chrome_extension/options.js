document.addEventListener('DOMContentLoaded', () => {
  // Load saved settings
  loadSavedSettings();
  
  // Set up event listeners for settings changes
  document.getElementById('serverUrl').addEventListener('change', saveSettings);
  document.getElementById('textSize').addEventListener('change', saveSettings);
  document.getElementById('overlayOpacity').addEventListener('input', saveSettings);
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
  const statusElem = document.getElementById('connectionStatus');
  
  statusElem.textContent = 'Testing connection...';
  statusElem.style.color = 'blue';
  
  let socket;
  let connectionTimeout;
  
  try {
    // Create WebSocket connection
    socket = new WebSocket(serverUrl);
    
    // Set timeout for connection
    connectionTimeout = setTimeout(() => {
      if (socket && socket.readyState !== WebSocket.OPEN) {
        socket.close();
        statusElem.textContent = 'Connection timed out after 5 seconds';
        statusElem.style.color = 'red';
      }
    }, 5000);
    
    // Connection successful
    socket.onopen = () => {
      clearTimeout(connectionTimeout);
      statusElem.textContent = 'WebSocket connection successful!';
      statusElem.style.color = 'green';
      
      // Close the socket after successful test
      setTimeout(() => {
        socket.close(1000, 'Test connection completed');
      }, 1000);
    };
    
    // Connection error
    socket.onerror = (error) => {
      clearTimeout(connectionTimeout);
      statusElem.textContent = 'Connection failed: Could not connect to server';
      statusElem.style.color = 'red';
      console.error('WebSocket test error:', error);
    };
    
    // Connection closed
    socket.onclose = (event) => {
      // Only show closed message if it wasn't already successful
      if (statusElem.textContent !== 'WebSocket connection successful!') {
        statusElem.textContent = `Connection closed: ${event.code} ${event.reason || 'No reason provided'}`;
        statusElem.style.color = 'red';
      }
    };
    
  } catch (error) {
    clearTimeout(connectionTimeout);
    statusElem.textContent = `Connection error: ${error.message}`;
    statusElem.style.color = 'red';
    console.error('WebSocket creation error:', error);
  }
}