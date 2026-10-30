const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 0,
  use: { baseURL: 'http://127.0.0.1:8766', browserName: 'chromium', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: {
    command: 'python run.py',
    url: 'http://127.0.0.1:8766/api/snapshot',
    reuseExistingServer: false,
    timeout: 30000,
    env: { ORCHESTRA_DB: './e2e-registry.sqlite3', ORCHESTRA_PORT: '8766' }
  },
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
});
