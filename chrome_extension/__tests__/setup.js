// Mock Chrome API
global.chrome = {
  runtime: {
    onMessage: {
      addListener: jest.fn(),
      removeListener: jest.fn()
    },
    sendMessage: jest.fn()
  },
  storage: {
    sync: {
      get: jest.fn(),
      set: jest.fn()
    }
  }
};

// Create a simple DOM environment for testing
global.document = {
  createElement: jest.fn(),
  getElementById: jest.fn(),
  body: {
    appendChild: jest.fn(),
    removeChild: jest.fn()
  }
};

// Mock window object properties and methods needed for tests
global.window = {
  ...global,
  addEventListener: jest.fn(),
  removeEventListener: jest.fn(),
  setTimeout: jest.fn(),
  clearTimeout: jest.fn()
};

// Reset mocks before each test
beforeEach(() => {
  jest.clearAllMocks();
});