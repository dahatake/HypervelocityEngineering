/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: 'jsdom',
  testMatch: [
    '<rootDir>/src/test/ui/**/*.test.js'
  ],
  testPathIgnorePatterns: ['/node_modules/', '/e2e/'],
  setupFiles: ['whatwg-fetch'],
  transform: {},
  moduleFileExtensions: ['js', 'json'],
  resetMocks: true,
  clearMocks: true
};
