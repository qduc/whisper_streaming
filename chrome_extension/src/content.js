// Default configuration
const DEFAULT_CONFIG = {
    textSize: 'medium',
    overlayOpacity: 0.8,
    numOfLines: 3,
    minLengthToDisplay: 30,
    maxIdleTime: 1500, // 1.5 seconds in ms
    overlayHideTimeout: 15000 // 15 seconds in ms
};

class TranscriptionOverlay {
    constructor() {
        this.config = { ...DEFAULT_CONFIG };
        this.textBuffer = [];
        this.hideTimeoutId = null;
        this.accumulatedText = '';
        this.lastUpdateTime = Date.now();
        this.position = null;
        this.initialize();
    }

    initialize() {
        // Create overlay container
        this.overlay = document.createElement('div');
        this.overlay.id = 'whisper-transcription-overlay';
        this.applyOverlayStyles();
        
        // Create text container
        this.textContainer = document.createElement('div');
        this.textContainer.id = 'whisper-text-container';
        this.overlay.appendChild(this.textContainer);
        
        // Add to DOM but keep hidden
        document.body.appendChild(this.overlay);
        
        // Load saved position
        chrome.storage.sync.get(['overlayPosition'], (result) => {
            if (result.overlayPosition) {
                this.position = result.overlayPosition;
                this.applyPosition();
            }
        });

        // Load saved settings
        chrome.storage.sync.get(['transcriptionSettings'], (result) => {
            if (result.transcriptionSettings) {
                this.updateConfig(result.transcriptionSettings);
            }
        });

        this.setupDragging();
        this.setupMessageListeners();
    }

    applyOverlayStyles() {
        const styles = {
            position: 'fixed',
            bottom: '50px',
            left: '50%',
            transform: 'translateX(-50%)',
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            color: 'white',
            padding: '10px 20px',
            borderRadius: '8px',
            zIndex: '9999',
            transition: 'opacity 0.3s ease',
            maxWidth: '80%',
            display: 'none',
            cursor: 'move',
            userSelect: 'none',
            textShadow: '0px 1px 2px rgba(0, 0, 0, 0.8)',
            fontFamily: 'Arial, Helvetica, sans-serif',
            boxShadow: '0 4px 8px rgba(0, 0, 0, 0.3)'
        };

        Object.assign(this.overlay.style, styles);
    }

    setupDragging() {
        let isDragging = false;
        let currentX;
        let currentY;
        let initialX;
        let initialY;

        this.overlay.addEventListener('mousedown', (e) => {
            isDragging = true;
            initialX = e.clientX - this.overlay.offsetLeft;
            initialY = e.clientY - this.overlay.offsetTop;
        });

        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                e.preventDefault();
                currentX = e.clientX - initialX;
                currentY = e.clientY - initialY;

                // Constrain to viewport
                currentX = Math.max(0, Math.min(currentX, window.innerWidth - this.overlay.offsetWidth));
                currentY = Math.max(0, Math.min(currentY, window.innerHeight - this.overlay.offsetHeight));

                this.position = { x: currentX, y: currentY };
                this.applyPosition();
            }
        });

        document.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                // Save position
                chrome.storage.sync.set({ overlayPosition: this.position });
            }
        });
    }

    applyPosition() {
        if (this.position) {
            this.overlay.style.left = `${this.position.x}px`;
            this.overlay.style.top = `${this.position.y}px`;
            this.overlay.style.transform = 'none';
        }
    }

    setupMessageListeners() {
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            switch (message.action) {
                case 'updateTranscription':
                    this.processTranscription(message.text);
                    break;
                case 'showOverlay':
                    this.show();
                    break;
                case 'hideOverlay':
                    this.hide();
                    break;
                case 'settingsUpdated':
                    this.updateConfig(message.settings);
                    break;
            }
            sendResponse({ success: true });
        });
    }

    processTranscription(text) {
        this.accumulatedText += text;
        const currentTime = Date.now();
        
        if (this.accumulatedText.length >= this.config.minLengthToDisplay ||
            currentTime - this.lastUpdateTime >= this.config.maxIdleTime) {
            this.updateDisplay(this.accumulatedText);
            this.accumulatedText = '';
            this.lastUpdateTime = currentTime;
        }
    }

    updateDisplay(text) {
        if (!text.trim()) return;

        this.textBuffer.push(text);
        while (this.textBuffer.length > this.config.numOfLines) {
            this.textBuffer.shift();
        }

        this.textContainer.innerHTML = this.textBuffer.map((line, index) => {
            const opacity = 0.5 + (0.5 * (index / (this.textBuffer.length - 1)));
            return `<div style="opacity: ${opacity}; margin-bottom: 5px; text-shadow: 0px 0px 1px #000, 0px 0px 2px #000; letter-spacing: 0.3px;">${line}</div>`;
        }).join('');

        this.show();
    }

    show() {
        this.overlay.style.display = 'block';
        this.resetHideTimeout();
    }

    hide() {
        this.overlay.style.display = 'none';
        this.textBuffer = [];
        this.accumulatedText = '';
    }

    resetHideTimeout() {
        if (this.hideTimeoutId) {
            clearTimeout(this.hideTimeoutId);
        }
        this.hideTimeoutId = setTimeout(() => this.hide(), this.config.overlayHideTimeout);
    }

    updateConfig(newConfig) {
        this.config = { ...this.config, ...newConfig };
        this.applyConfig();
    }

    applyConfig() {
        // Apply text size
        const fontSizes = {
            small: '14px',
            medium: '18px',
            large: '24px'
        };
        this.textContainer.style.fontSize = fontSizes[this.config.textSize];
        
        // Apply opacity
        this.overlay.style.backgroundColor = `rgba(0, 0, 0, ${this.config.overlayOpacity})`;
        
        // Apply enhanced readability styles
        this.textContainer.style.lineHeight = '1.4';
        this.textContainer.style.fontWeight = '500';
        this.textContainer.style.textAlign = 'center';
    }
}

// Initialize overlay when content script loads
const transcriptionOverlay = new TranscriptionOverlay();