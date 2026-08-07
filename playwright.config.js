const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testMatch: ['**/src/test/ui/**/*.spec.js'],
  use: {
    baseURL: 'http://localhost:3000',
  },
  webServer: {
    command: 'npx serve src/app -p 3000',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
