// Import the content script
// Note: We're testing the content script in isolation, so we need to mock all its dependencies
const fs = require('fs');
const path = require('path');
const contentScriptPath = path.resolve(__dirname, '../content.js');
const contentScriptCode = fs.readFileSync(contentScriptPath, 'utf8');

describe('Content Script', () => {
  // Set up DOM elements and spies before each test
  let mockOverlay;
  let mockTextContainer;

  beforeEach(() => {
    // Reset mocks
    jest.resetAllMocks();

    // Reset DOM
    document.body.innerHTML = '';

    // Mock chrome.storage.sync.get to return settings
    chrome.storage.sync.get.mockImplementation((key, callback) => {
      if (key === 'settings') {
        callback({
          settings: {
            textSize: 'medium',
            overlayOpacity: 0.8,
            shortChunkThreshold: 15,
            longChunkThreshold: 80,
            maxLineLength: 100,
            numOfLines: 3,
            minLengthToDisplay: 30,
            maxIdleTime: 1.5,
            overlayHideTimeout: 15
          }
        });
      }
    });

    // Enhanced DOM mocking
    document.createElement = jest.fn().mockImplementation((tagName) => {
      const element = {
        id: '',
        style: {},
        classList: {
          add: jest.fn(),
          remove: jest.fn(),
          contains: jest.fn()
        },
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        appendChild: jest.fn(),
        innerHTML: '',
        textContent: '',
        getBoundingClientRect: jest.fn().mockReturnValue({
          width: 300,
          height: 200,
          top: 100,
          left: 100,
          right: 400,
          bottom: 300
        }),
        parentNode: {
          removeChild: jest.fn()
        }
      };

      if (tagName === 'div' && !mockOverlay) {
        mockOverlay = element;
        return mockOverlay;
      } else if (tagName === 'div' && mockOverlay && !mockTextContainer) {
        mockTextContainer = element;
        return mockTextContainer;
      }

      return element;
    });

    document.getElementById = jest.fn().mockImplementation((id) => {
      if (id === 'whisper-transcription-overlay') return mockOverlay;
      if (id === 'whisper-transcription-text') return mockTextContainer;
      return null;
    });

    document.body.appendChild = jest.fn();

    // Mock setTimeout and clearTimeout
    jest.useFakeTimers();

    // Create a wrapper to expose window-scoped functions for testing
    const wrapContentScript = `
      (function() {
        // Store original window object
        const originalWindow = window;

        // Execute the content script in this scope
        ${contentScriptCode}

        // Make window-scoped functions accessible for testing
        window.testHelpers = {
          initialize,
          createOverlay,
          showOverlay,
          hideOverlay,
          updateTranscriptionText,
          updateTextDisplay,
          applySettings,
          startDragging,
          handleDrag,
          stopDragging,
          handleWindowResize,
          resetHideTimer,
          loadSettings,
          initializeBuffer,
          ensureOverlayExists,
          cleanup
        };

        // Copy all testHelpers to global scope for easier access in tests
        Object.keys(window.testHelpers).forEach(key => {
          global[key] = window.testHelpers[key];
        });
      })();
    `;

    // Execute the wrapped content script code
    eval(wrapContentScript);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('Initialization', () => {
    it('should create overlay elements on initialization', () => {
      // The initialize function should have been called, which calls createOverlay
      expect(document.createElement).toHaveBeenCalledWith('div');
      expect(document.body.appendChild).toHaveBeenCalled();
    });

    it('should load settings on initialization', () => {
      expect(chrome.storage.sync.get).toHaveBeenCalledWith('settings', expect.any(Function));
    });

    it('should add message listener on initialization', () => {
      expect(chrome.runtime.onMessage.addListener).toHaveBeenCalled();
    });
  });

  describe('Message Handling', () => {
    let messageListener;

    beforeEach(() => {
      // Extract the message listener function
      messageListener = chrome.runtime.onMessage.addListener.mock.calls[0][0];
    });

    it('should handle updateTranscription messages', () => {
      // Create a spy on the updateTranscriptionText function
      const updateSpy = jest.spyOn(window, 'updateTranscriptionText');

      // Call the message listener with an updateTranscription message
      messageListener({
        action: 'updateTranscription',
        text: 'Hello world'
      });

      expect(updateSpy).toHaveBeenCalledWith({
        action: 'updateTranscription',
        text: 'Hello world'
      });
    });

    it('should handle showOverlay messages', () => {
      // Create a spy on the showOverlay function
      const showSpy = jest.spyOn(window, 'showOverlay');

      // Call the message listener with a showOverlay message
      messageListener({
        action: 'showOverlay',
        settings: {
          textSize: 'large'
        }
      });

      expect(showSpy).toHaveBeenCalledWith(true);
    });

    it('should handle hideOverlay messages', () => {
      // Create a spy on the hideOverlay function
      const hideSpy = jest.spyOn(window, 'hideOverlay');

      // Call the message listener with a hideOverlay message
      messageListener({
        action: 'hideOverlay'
      });

      expect(hideSpy).toHaveBeenCalled();
    });

    it('should handle settingsUpdated messages', () => {
      // Create a spy on the applySettings function
      const applySpy = jest.spyOn(window, 'applySettings');

      // Call the message listener with a settingsUpdated message
      messageListener({
        action: 'settingsUpdated',
        settings: {
          textSize: 'large'
        }
      });

      // Check if settings were updated
      expect(window.currentSettings.textSize).toBe('large');
      expect(applySpy).toHaveBeenCalled();
    });
  });

  describe('Transcription Text Handling', () => {
    beforeEach(() => {
      // Reset current state
      window.textBuffer = new Array(window.currentSettings.numOfLines).fill('');
      window.currentText = '';
      window.lastUpdateTime = 0;
    });

    it('should accumulate text until minimum length is reached', () => {
      // Spy on updateTextDisplay
      const displaySpy = jest.spyOn(window, 'updateTextDisplay');

      // Send short updates that don't reach minimum length
      window.updateTranscriptionText({ text: 'Short ' });
      window.updateTranscriptionText({ text: 'text ' });

      // Text should be accumulated but not displayed yet
      expect(window.currentText).toBe('Short text ');
      expect(displaySpy).not.toHaveBeenCalled();

      // Send update that makes it reach minimum length
      window.updateTranscriptionText({ text: 'that reaches minimum length' });

      // Now text should be displayed
      expect(displaySpy).toHaveBeenCalled();
      expect(window.textBuffer[window.textBuffer.length - 1]).toBe('Short text that reaches minimum length');
    });

    it('should update display after maxIdleTime even if text is short', () => {
      // Spy on updateTextDisplay
      const displaySpy = jest.spyOn(window, 'updateTextDisplay');

      // Send a short update
      window.updateTranscriptionText({ text: 'Short text' });

      // Text should be accumulated but not displayed yet
      expect(window.currentText).toBe('Short text');
      expect(displaySpy).not.toHaveBeenCalled();

      // Advance time past maxIdleTime
      jest.advanceTimersByTime(window.currentSettings.maxIdleTime * 1000 + 100);

      // Now text should be displayed
      expect(displaySpy).toHaveBeenCalled();
    });

    it('should handle translation text differently', () => {
      const displaySpy = jest.spyOn(window, 'updateTextDisplay');

      // Send a translation update
      window.updateTranscriptionText({
        text: 'Translated text',
        isTranslation: true
      });

      // For translations, text should replace current text, not append
      expect(window.currentText).toBe('Translated text');

      // Since it's short, it shouldn't update display yet
      expect(displaySpy).not.toHaveBeenCalled();

      // Send another longer translation that exceeds minimum length
      window.updateTranscriptionText({
        text: 'This is a much longer translated text that exceeds the minimum length requirement',
        isTranslation: true
      });

      // Text should be replaced and display updated
      expect(window.currentText).toBe('This is a much longer translated text that exceeds the minimum length requirement');
      expect(displaySpy).toHaveBeenCalled();
    });
  });

  describe('Overlay Management', () => {
    it('should show overlay with correct positioning', () => {
      // Call showOverlay
      window.showOverlay();

      // Check that overlay is displayed
      expect(mockOverlay.style.display).toBe('flex');
      expect(window.isVisible).toBe(true);
    });

    it('should hide overlay', () => {
      // First show the overlay
      window.showOverlay();

      // Then hide it
      window.hideOverlay();

      // Check that overlay is hidden
      expect(mockOverlay.style.display).toBe('none');
      expect(window.isVisible).toBe(false);
    });

    it('should automatically hide overlay after timeout', () => {
      // Show the overlay
      window.showOverlay();

      // Advance time just before timeout
      jest.advanceTimersByTime(window.currentSettings.overlayHideTimeout * 1000 - 100);

      // Overlay should still be visible
      expect(mockOverlay.style.display).toBe('flex');

      // Advance time past timeout
      jest.advanceTimersByTime(200);

      // Overlay should now be hidden
      expect(mockOverlay.style.display).toBe('none');
    });
  });

  describe('Settings Application', () => {
    it('should apply text size settings', () => {
      // Update settings
      window.currentSettings.textSize = 'large';

      // Apply settings
      window.applySettings();

      // Check that text size was applied
      expect(mockTextContainer.style.fontSize).toBe('22px');

      // Try small size
      window.currentSettings.textSize = 'small';
      window.applySettings();
      expect(mockTextContainer.style.fontSize).toBe('14px');
    });

    it('should apply opacity settings', () => {
      // Update settings
      window.currentSettings.overlayOpacity = 0.5;

      // Apply settings
      window.applySettings();

      // Check that opacity was applied
      expect(mockOverlay.style.opacity).toBe(0.5);
    });

    it('should update buffer size when numOfLines changes', () => {
      // Initialize with 3 lines
      window.textBuffer = ['Line 1', 'Line 2', 'Line 3'];

      // Change to 5 lines
      window.currentSettings.numOfLines = 5;

      // Apply settings
      window.applySettings();

      // Check that buffer size was updated
      expect(window.textBuffer.length).toBe(5);

      // Check that existing lines were preserved (in the right positions)
      expect(window.textBuffer[2]).toBe('Line 1');
      expect(window.textBuffer[3]).toBe('Line 2');
      expect(window.textBuffer[4]).toBe('Line 3');
      expect(window.textBuffer[0]).toBe('');
      expect(window.textBuffer[1]).toBe('');
    });
  });

  describe('Drag Functionality', () => {
    it('should start dragging on mousedown', () => {
      // Get the mousedown listener
      const mousedownListener = mockOverlay.addEventListener.mock.calls.find(
        call => call[0] === 'mousedown'
      )[1];

      // Create a mock event
      const mockEvent = {
        clientX: 150,
        clientY: 120,
        preventDefault: jest.fn()
      };

      // Call the listener
      mousedownListener(mockEvent);

      // Check that dragging started
      expect(window.isDragging).toBe(true);
      expect(typeof window.dragOffset.x).toBe('number');
      expect(typeof window.dragOffset.y).toBe('number');
      expect(mockEvent.preventDefault).toHaveBeenCalled();
    });

    it('should update position while dragging', () => {
      // Start dragging
      window.isDragging = true;
      window.dragOffset = { x: 50, y: 50 };

      // Create a mock mousemove event
      const mockEvent = {
        clientX: 200,
        clientY: 150
      };

      // Call handleDrag
      window.handleDrag(mockEvent);

      // Check that position was updated
      expect(mockOverlay.style.left).toBe('150px'); // 200 - 50
      expect(mockOverlay.style.top).toBe('100px');  // 150 - 50
    });

    it('should stop dragging on mouseup', () => {
      // Start dragging
      window.isDragging = true;
      mockOverlay.style.left = '150px';
      mockOverlay.style.top = '100px';

      // Call stopDragging
      window.stopDragging();

      // Check that dragging stopped
      expect(window.isDragging).toBe(false);
      expect(window.overlayPosition.left).toBe('150px');
      expect(window.overlayPosition.top).toBe('100px');
    });
  });
});