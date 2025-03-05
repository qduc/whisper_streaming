// Audio processor for WhisperLive Chrome extension
// Handles audio capture and conversion for streaming to WebSocket

// Constants for audio processing
const SAMPLE_RATE = 16000; // Whisper expects 16kHz audio
const PROCESSOR_BUFFER_SIZE = 4096;
const SEND_INTERVAL_MS = 500; // Send audio every 500ms

/**
 * Process audio from the captured media stream and send to websocket
 * @param {MediaStream} mediaStream - The captured tab audio stream
 * @param {AudioContext} audioContext - Web Audio API context
 * @param {Object} websocket - WebSocket client instance
 * @returns {Promise} - Resolves when setup is complete
 */
export async function processAudio(mediaStream, audioContext, websocket) {
  return new Promise((resolve) => {
    // Create source from the media stream
    const source = audioContext.createMediaStreamSource(mediaStream);
    
    // Create a script processor node for raw PCM data access
    const processor = audioContext.createScriptProcessor(
      PROCESSOR_BUFFER_SIZE,
      1, // Input channel count (mono)
      1  // Output channel count (mono)
    );
    
    // Audio buffer for collecting samples between sends
    let audioChunks = [];
    let lastSendTime = Date.now();
    
    // Setup resampler if needed
    const needsResampling = audioContext.sampleRate !== SAMPLE_RATE;
    let resampler = null;
    
    if (needsResampling) {
      console.log(`Resampling from ${audioContext.sampleRate}Hz to ${SAMPLE_RATE}Hz`);
    }
    
    // Process audio data
    processor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);
      const audioData = needsResampling ? 
        resampleAudio(inputData, audioContext.sampleRate, SAMPLE_RATE) : 
        inputData;
        
      // Add processed data to chunks
      audioChunks.push(new Float32Array(audioData));
      
      // Send audio chunks at regular intervals
      const now = Date.now();
      if (now - lastSendTime >= SEND_INTERVAL_MS) {
        sendAudioChunks();
        lastSendTime = now;
      }
    };
    
    /**
     * Sends collected audio chunks via WebSocket
     */
    function sendAudioChunks() {
      if (audioChunks.length === 0 || !websocket.isConnected()) return;
      
      // Concatenate all chunks into a single Float32Array
      const totalLength = audioChunks.reduce((len, chunk) => len + chunk.length, 0);
      const concatenated = new Float32Array(totalLength);
      
      let offset = 0;
      for (const chunk of audioChunks) {
        concatenated.set(chunk, offset);
        offset += chunk.length;
      }
      
      // Convert to 16-bit PCM
      const pcmData = floatTo16BitPCM(concatenated);
      
      // Send via websocket
      websocket.sendAudio(pcmData);
      
      // Clear the chunks
      audioChunks = [];
    }
    
    // Connect nodes: source -> processor -> destination
    source.connect(processor);
    processor.connect(audioContext.destination);
    
    // Clean up function to stop processing
    websocket.onDisconnect(() => {
      processor.disconnect();
      source.disconnect();
    });
    
    resolve();
  });
}

/**
 * Simple linear resampling of audio data
 * @param {Float32Array} audioData - Original audio data
 * @param {number} originalSampleRate - Original sample rate
 * @param {number} targetSampleRate - Target sample rate
 * @returns {Float32Array} - Resampled audio data
 */
function resampleAudio(audioData, originalSampleRate, targetSampleRate) {
  const ratio = originalSampleRate / targetSampleRate;
  const newLength = Math.round(audioData.length / ratio);
  const result = new Float32Array(newLength);
  
  for (let i = 0; i < newLength; i++) {
    const position = i * ratio;
    const index = Math.floor(position);
    const fraction = position - index;
    
    // Simple linear interpolation
    if (index + 1 < audioData.length) {
      result[i] = audioData[index] * (1 - fraction) + audioData[index + 1] * fraction;
    } else {
      result[i] = audioData[index];
    }
  }
  
  return result;
}

/**
 * Convert Float32Array audio data to 16-bit PCM
 * @param {Float32Array} float32Array - Audio data as float
 * @returns {Int16Array} - Audio data as 16-bit PCM
 */
function floatTo16BitPCM(float32Array) {
  const int16Array = new Int16Array(float32Array.length);
  
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  
  return int16Array;
}