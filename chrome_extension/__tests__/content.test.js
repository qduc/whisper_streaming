/**
 * @jest-environment jsdom
 */

// Mock chrome API
global.chrome = {
    runtime: {
        onMessage: {
            addListener: jest.fn()
        }
    },
    storage: {
        sync: {
            get: jest.fn(),
            set: jest.fn()
        }
    }
};

// Import the TranscriptionOverlay class
const fs = require('fs');
const path = require('path');
const contentJs = fs.readFileSync(path.resolve(__dirname, '../src/content.js'), 'utf8');
eval(contentJs);

describe('TranscriptionOverlay', () => {
    let overlay;
    
    beforeEach(() => {
        // Clear all mocks
        jest.clearAllMocks();
        
        // Reset DOM
        document.body.innerHTML = '';
        
        // Mock chrome.storage.sync.get to return empty results
        chrome.storage.sync.get.mockImplementation((keys, callback) => {
            callback({});
        });
        
        // Initialize new overlay instance
        overlay = new TranscriptionOverlay();
    });

    describe('Initialization', () => {
        test('should create overlay elements', () => {
            const overlayElement = document.getElementById('whisper-transcription-overlay');
            const textContainer = document.getElementById('whisper-text-container');
            
            expect(overlayElement).toBeTruthy();
            expect(textContainer).toBeTruthy();
            expect(overlayElement.contains(textContainer)).toBeTruthy();
        });

        test('should load saved position from storage', () => {
            const savedPosition = { x: 100, y: 200 };
            chrome.storage.sync.get.mockImplementation((keys, callback) => {
                callback({ overlayPosition: savedPosition });
            });

            const newOverlay = new TranscriptionOverlay();
            expect(chrome.storage.sync.get).toHaveBeenCalledWith(['overlayPosition'], expect.any(Function));
        });

        test('should load saved settings from storage', () => {
            const savedSettings = {
                textSize: 'large',
                overlayOpacity: 0.5
            };
            chrome.storage.sync.get.mockImplementation((keys, callback) => {
                callback({ transcriptionSettings: savedSettings });
            });

            const newOverlay = new TranscriptionOverlay();
            expect(chrome.storage.sync.get).toHaveBeenCalledWith(['transcriptionSettings'], expect.any(Function));
        });
    });

    describe('Message handling', () => {
        test('should process updateTranscription message', () => {
            const mockMessage = {
                action: 'updateTranscription',
                text: 'Test transcription'
            };
            
            // Mock the message listener callback
            const messageCallback = chrome.runtime.onMessage.addListener.mock.calls[0][0];
            const mockSendResponse = jest.fn();
            
            messageCallback(mockMessage, {}, mockSendResponse);
            
            // Verify the text is displayed after reaching minLengthToDisplay
            const repeatedText = 'Test transcription'.repeat(2); // Make it longer than minLengthToDisplay
            messageCallback({ action: 'updateTranscription', text: repeatedText }, {}, mockSendResponse);
            
            const textContainer = document.getElementById('whisper-text-container');
            expect(textContainer.innerHTML).toContain(repeatedText);
        });

        test('should handle show/hide overlay messages', () => {
            const mockSendResponse = jest.fn();
            const messageCallback = chrome.runtime.onMessage.addListener.mock.calls[0][0];
            
            // Test show
            messageCallback({ action: 'showOverlay' }, {}, mockSendResponse);
            expect(overlay.overlay.style.display).toBe('block');
            
            // Test hide
            messageCallback({ action: 'hideOverlay' }, {}, mockSendResponse);
            expect(overlay.overlay.style.display).toBe('none');
        });

        test('should update settings when receiving settingsUpdated message', () => {
            const newSettings = {
                textSize: 'large',
                overlayOpacity: 0.5
            };
            
            const messageCallback = chrome.runtime.onMessage.addListener.mock.calls[0][0];
            const mockSendResponse = jest.fn();
            
            messageCallback({ 
                action: 'settingsUpdated',
                settings: newSettings
            }, {}, mockSendResponse);
            
            expect(overlay.config.textSize).toBe('large');
            expect(overlay.config.overlayOpacity).toBe(0.5);
        });
    });

    describe('Text processing', () => {
        test('should accumulate text until minimum length', () => {
            const shortText = 'Short';
            overlay.processTranscription(shortText);
            
            const textContainer = document.getElementById('whisper-text-container');
            expect(textContainer.innerHTML).toBe(''); // Should not display yet
            
            const longText = 'This is a much longer text that exceeds the minimum length requirement';
            overlay.processTranscription(longText);
            expect(textContainer.innerHTML).toContain(longText);
        });

        test('should maintain correct number of text lines', () => {
            const messageCallback = chrome.runtime.onMessage.addListener.mock.calls[0][0];
            const mockSendResponse = jest.fn();
            
            // Add more lines than config.numOfLines
            for (let i = 1; i <= 5; i++) {
                messageCallback({
                    action: 'updateTranscription',
                    text: `Test line ${i}`.repeat(10) // Make it longer than minLengthToDisplay
                }, {}, mockSendResponse);
            }
            
            const textContainer = document.getElementById('whisper-text-container');
            const lines = textContainer.getElementsByTagName('div');
            expect(lines.length).toBeLessThanOrEqual(overlay.config.numOfLines);
        });
    });

    describe('Auto-hide behavior', () => {
        beforeEach(() => {
            jest.useFakeTimers();
        });

        afterEach(() => {
            jest.useRealTimers();
        });

        test('should auto-hide after timeout', () => {
            overlay.show();
            expect(overlay.overlay.style.display).toBe('block');
            
            jest.advanceTimersByTime(overlay.config.overlayHideTimeout);
            expect(overlay.overlay.style.display).toBe('none');
        });

        test('should reset hide timeout on new content', () => {
            overlay.show();
            jest.advanceTimersByTime(overlay.config.overlayHideTimeout - 1000);
            
            // Show new content
            overlay.show();
            jest.advanceTimersByTime(overlay.config.overlayHideTimeout - 1000);
            expect(overlay.overlay.style.display).toBe('block');
            
            // Should hide after full timeout
            jest.advanceTimersByTime(1000);
            expect(overlay.overlay.style.display).toBe('none');
        });
    });

    describe('Dragging functionality', () => {
        test('should update position on drag', () => {
            const mousedownEvent = new MouseEvent('mousedown', {
                clientX: 100,
                clientY: 100
            });
            
            const mousemoveEvent = new MouseEvent('mousemove', {
                clientX: 200,
                clientY: 200
            });
            
            const mouseupEvent = new MouseEvent('mouseup');
            
            overlay.overlay.dispatchEvent(mousedownEvent);
            document.dispatchEvent(mousemoveEvent);
            document.dispatchEvent(mouseupEvent);
            
            expect(chrome.storage.sync.set).toHaveBeenCalled();
        });
    });
});