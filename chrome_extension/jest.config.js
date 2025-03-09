module.exports = {
  testEnvironment: 'jsdom',
  transform: {
    '^.+\\.js$': 'babel-jest'
  },
  moduleFileExtensions: ['js'],
  moduleDirectories: ['node_modules'],
  testPathIgnorePatterns: ['/node_modules/', 'setup.js'],
  testMatch: ['**/__tests__/**/*.test.js'],
  // setupFilesAfterEnv: ['<rootDir>/__tests__/setup.js'],
};