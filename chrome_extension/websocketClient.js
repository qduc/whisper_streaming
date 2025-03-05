/**
 * WebSocket client for WhisperLive Chrome extension
 * Handles communication with the Whisper server
 */
export class WebSocketClient {
  /**
   * Create a new WebSocket client
   * @param {string} url - WebSocket server URL
   */
  constructor(url) {
    this.url = url;
    this.socket = null;
    this.isConnected = false;
    this.messageHandler = null;
    this.disconnectHandler = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 3;
    this.reconnectDelay = 1000; // 1 second initial delay
  }

  /**
   * Connect to the WebSocket server
   * @returns {Promise} - Resolves when connected, rejects on failure
   */
  connect() {
    return new Promise((resolve, reject) => {
      try {
        this.socket = new WebSocket(this.url);
        
        // Set up event handlers
        this.socket.onopen = () => {
          console.log('WebSocket connected to', this.url);
          this.isConnected = true;
          this.reconnectAttempts = 0;
          resolve();
        };
        
        this.socket.onclose = (event) => {
          console.log(`WebSocket closed: ${event.code} ${event.reason}`);
          this.isConnected = false;
          
          // Try to reconnect if it wasn't a normal closure
          if (event.code !== 1000 && event.code !== 1001) {
            this.attemptReconnect();
          }
          
          if (this.disconnectHandler) {
            this.disconnectHandler();
          }
        };
        
        this.socket.onerror = (error) => {
          console.error('WebSocket error:', error);
          if (this.socket.readyState === WebSocket.CONNECTING) {
            reject(new Error('Failed to connect to WebSocket server'));
          }
        };
        
        this.socket.onmessage = (event) => {
          this.handleMessage(event.data);
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Handle incoming messages from the server
   * @param {string} data - Message data
   */
  handleMessage(data) {
    try {
      const message = JSON.parse(data);
      
      if (this.messageHandler) {
        this.messageHandler(message);
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  }

  /**
   * Attempt to reconnect to the server
   */
  attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Maximum reconnect attempts reached');
      return;
    }
    
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    
    console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    setTimeout(() => {
      if (!this.isConnected) {
        this.connect().catch(error => {
          console.error('Reconnect failed:', error);
        });
      }
    }, delay);
  }

  /**
   * Send audio data to the server
   * @param {Int16Array} audioData - 16-bit PCM audio data
   */
  sendAudio(audioData) {
    if (!this.isConnected || !this.socket) {
      return;
    }
    
    // Convert Int16Array to ArrayBuffer for sending
    const audioBuffer = audioData.buffer;
    
    try {
      this.socket.send(audioBuffer);
    } catch (error) {
      console.error('Error sending audio data:', error);
    }
  }

  /**
   * Set message handler callback
   * @param {Function} handler - Function to call with parsed messages
   */
  onMessage(handler) {
    this.messageHandler = handler;
  }

  /**
   * Set disconnect handler callback
   * @param {Function} handler - Function to call when connection closes
   */
  onDisconnect(handler) {
    this.disconnectHandler = handler;
  }

  /**
   * Check if socket is connected
   * @returns {boolean} - True if connected
   */
  isConnected() {
    return this.isConnected && this.socket && this.socket.readyState === WebSocket.OPEN;
  }

  /**
   * Disconnect from the server
   * @returns {Promise} - Resolves when disconnected
   */
  disconnect() {
    return new Promise((resolve) => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        this.isConnected = false;
        resolve();
        return;
      }
      
      // Set up one-time event handler for close event
      const onClose = () => {
        this.socket.removeEventListener('close', onClose);
        this.isConnected = false;
        resolve();
      };
      
      this.socket.addEventListener('close', onClose);
      
      // Close the connection
      this.socket.close(1000, 'Client disconnected');
    });
  }
}