document.addEventListener('DOMContentLoaded', () => {
  const serverUrlInput = document.getElementById('serverUrl');
  const saveButton = document.getElementById('saveButton');

  // Load saved settings
  chrome.storage.sync.get('settings', (data) => {
    if (data.settings && data.settings.serverUrl) {
      serverUrlInput.value = data.settings.serverUrl;
    }
  });

  // Save settings
  saveButton.addEventListener('click', () => {
    const serverUrl = serverUrlInput.value;
    chrome.storage.sync.set({ settings: { serverUrl } }, () => {
      alert('Settings saved');
    });
  });
});